# -*- coding: utf-8 -*-
# @Author  : relakkes@gmail.com
# @Time    : 2023/12/2 18:44
# @Desc    : B站爬虫

import asyncio
import json
import os
import random
from asyncio import Task
from typing import Dict, List, Optional, Tuple, Any

from playwright.async_api import (BrowserContext, BrowserType, Page,
                                  async_playwright)

import config
from base.base_crawler import AbstractCrawler
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import bilibili as bilibili_store
from tools import utils
from var import crawler_type_var, media_crawler_db_var
from db import AsyncMysqlDB

from .client import BilibiliClient
from .exception import DataFetchError
from .field import SearchOrderType
from .login import BilibiliLogin


class BilibiliCrawler(AbstractCrawler):
    platform: str
    login_type: str
    crawler_type: str
    context_page: Page
    bili_client: BilibiliClient
    browser_context: BrowserContext

    def __init__(self):
        self.index_url = "https://www.bilibili.com"
        self.user_agent = utils.get_user_agent()

    def init_config(self, platform: str, login_type: str, crawler_type: str, start_page: int, keyword: str):
        self.platform = platform
        self.login_type = login_type
        self.crawler_type = crawler_type
        self.start_page = start_page
        self.keyword = keyword

    async def start(self):
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
            ip_proxy_info: IpInfoModel = await ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = self.format_proxy_info(ip_proxy_info)

        async with async_playwright() as playwright:
            # Launch a browser context.
            chromium = playwright.chromium
            self.browser_context = await self.launch_browser(
                chromium,
                None,
                self.user_agent,
                headless=config.HEADLESS
            )
            # stealth.min.js is a js script to prevent the website from detecting the crawler.
            await self.browser_context.add_init_script(path="libs/stealth.min.js")
            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url)

            # Create a client to interact with the xiaohongshu website.
            self.bili_client = await self.create_bilibili_client(httpx_proxy_format)
            if not await self.bili_client.pong():
                login_obj = BilibiliLogin(
                    login_type=self.login_type,
                    login_phone="",  # your phone number
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=config.COOKIES
                )
                await login_obj.begin()
                await self.bili_client.update_cookies(browser_context=self.browser_context)

            crawler_type_var.set(self.crawler_type)
            if self.crawler_type == "search":
                # Search for video and retrieve their comment information.
                await self.search()
            elif self.crawler_type == "detail":
                # Get the information and comments of the specified post
                pass
            elif self.crawler_type == "user":
                # 根据用户id, 爬取用户信息
                await self.get_userinfo_by_user_id()
            elif self.crawler_type == "video_list_by_user_id":
                # 根据用户id, 爬取用户作品列表
                await self.get_video_list_by_user_id()
            elif self.crawler_type == "video_detail_by_video_id":
                # 根据作品id, 爬取用户作品详情
                await self.get_specified_videos()
            elif self.crawler_type == "comment":
                # 根据作品id, 爬取用户作品comment
                await self.get_video_comments()
            else:
                utils.logger.warn("[BilibiliCrawler.start] Bilibili Crawler unsupported crawler type")
            utils.logger.info("[BilibiliCrawler.start] Bilibili Crawler finished ...")

    async def search(self):
        """
        search bilibili video with keywords
        :return:
        """
        utils.logger.info("[BilibiliCrawler.search] Begin search bilibli keywords")
        bili_limit_count = 20  # bilibili limit page fixed value
        if config.CRAWLER_MAX_NOTES_COUNT < bili_limit_count:
            config.CRAWLER_MAX_NOTES_COUNT = bili_limit_count
        start_page = self.start_page  # start page number
        for keyword in self.keyword.split(","):
            utils.logger.info(f"[BilibiliCrawler.search] Current search keyword: {keyword}")
            page = 1
            while (page - start_page + 1) * bili_limit_count <= config.CRAWLER_MAX_NOTES_COUNT:
                if page < start_page:
                    utils.logger.info(f"[BilibiliCrawler.search] Skip page: {page}")
                    page += 1
                    continue

                video_id_list: List[str] = []
                videos_res = await self.bili_client.search_video_by_keyword(
                    keyword=keyword,
                    page=page,
                    page_size=bili_limit_count,
                    order=SearchOrderType.DEFAULT,
                )
                video_list: List[Dict] = videos_res.get("result")

                semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
                task_list = [
                    self.get_video_info_task(aid=video_item.get("aid"), bvid="", semaphore=semaphore)
                    for video_item in video_list
                ]
                video_items = await asyncio.gather(*task_list)
                for video_item in video_items:
                    if video_item:
                        video_id_list.append(video_item.get("View").get("aid"))
                        await bilibili_store.update_bilibili_video(video_item)

                page += 1
                await self.batch_get_video_comments(video_id_list)

    async def get_video_comments(self):
        if config.IS_PRODUCTION:
            async_db_conn: AsyncMysqlDB = media_crawler_db_var.get()
            result_row: List[Dict[str, Any]] = await async_db_conn.query("SELECT video_id FROM tb_bilibili_video;")
            print(len(result_row))
            task_ls = [item['video_id'] for item in result_row]
        else:
            task_ls = config.BILI_SPECIFIED_ID_LIST

        await self.batch_get_video_comments(task_ls)

    async def batch_get_video_comments(self, video_id_list: List[str]):
        """
        batch get video comments
        :param video_id_list:
        :return:
        """
        # if not config.ENABLE_GET_COMMENTS:
        #     utils.logger.info(f"[BilibiliCrawler.batch_get_note_comments] Crawling comment mode is not enabled")
        #     return

        utils.logger.info(f"[BilibiliCrawler.batch_get_video_comments] video ids:{video_id_list}")
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for video_id in video_id_list:
            task = asyncio.create_task(self.get_comments(video_id, semaphore), name=video_id)
            task_list.append(task)
        await asyncio.gather(*task_list)

    async def get_comments(self, video_id: str, semaphore: asyncio.Semaphore):
        """
        get comment for video id
        :param video_id:
        :param semaphore:
        :return:
        """
        async with semaphore:
            try:
                utils.logger.info(f"[BilibiliCrawler.get_comments] begin get video_id: {video_id} comments ...")
                await self.bili_client.get_video_all_comments(
                    video_id=video_id,
                    crawl_interval=random.random(),
                    callback=bilibili_store.batch_update_bilibili_video_comments
                )

            except DataFetchError as ex:
                utils.logger.error(f"[BilibiliCrawler.get_comments] get video_id: {video_id} comment error: {ex}")
            except Exception as e:
                utils.logger.error(f"[BilibiliCrawler.get_comments] may be been blocked, err:{e}")

    async def get_specified_videos(self):
        """
        get specified videos info
        :return:
        """
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)

        if config.IS_PRODUCTION:
            async_db_conn: AsyncMysqlDB = media_crawler_db_var.get()
            result_row: List[Dict[str, Any]] = await async_db_conn.query("SELECT video_id FROM tb_bilibili_video;")
            task_ls = [item['video_id'] for item in result_row]
        else:
            task_ls = config.BILI_SPECIFIED_ID_LIST

        task_list = [
            self.get_video_info_task(aid=video_id, bvid="", semaphore=semaphore) for video_id in
            task_ls
        ]
        video_details = await asyncio.gather(*task_list)
        for video_detail in video_details:
            if video_detail is not None:
                video_detail['status'] = 1
                await bilibili_store.update_bilibili_video(video_detail)

    async def get_video_info_task(self, aid: int, bvid: str, semaphore: asyncio.Semaphore) -> Optional[Dict]:
        """
        Get video detail task
        :param aid:
        :param bvid:
        :param semaphore:
        :return:
        """
        async with semaphore:
            try:
                result = await self.bili_client.get_video_info(aid=aid, bvid=bvid)
                return result
            except DataFetchError as ex:
                utils.logger.error(f"[BilibiliCrawler.get_video_info_task] Get video detail error: {ex}")
                return None
            except KeyError as ex:
                utils.logger.error(
                    f"[BilibiliCrawler.get_video_info_task] have not fund note detail video_id:{bvid}, err: {ex}")
                return None

    async def get_video_list_by_user_id_task(self, user_id: str, semaphore: asyncio.Semaphore):
        """
        Get video info task
        :param user_id:
        :param semaphore:
        :return:
        """
        async with semaphore:
            try:
                page_number: int = 0
                while True:
                    result, has_next, page_number = await self.bili_client.get_video_list_by_user_id(
                        user_id=user_id,
                        page_number=page_number + 1
                    )
                    yield result

                    if not has_next:
                        utils.logger.info(
                            f"[BilibiliCrawler.get_video_list_by_user_id_task] not next, current_page_number:{page_number}")
                        break
                    else:
                        utils.logger.info(
                            f"[BilibiliCrawler.get_video_list_by_user_id_task] have next, current_page_number:{page_number}")
                        await asyncio.sleep(10)
                        continue
            except DataFetchError as ex:
                utils.logger.error(f"[BilibiliCrawler.get_video_list_by_user_id_task] Get video list error: {ex}")
            except KeyError as ex:
                utils.logger.error(
                    f"[BilibiliCrawler.get_video_list_by_user_id_task] have not found  user_id:{user_id}, err: {ex}")

    async def get_video_list_by_user_id(self):
        """输入: user_id； 输出: video_id_list
        :return:
        """
        if config.IS_PRODUCTION:
            async_db_conn: AsyncMysqlDB = media_crawler_db_var.get()
            result_row: List[Dict[str, Any]] = await async_db_conn.query("SELECT user_id FROM tb_bilibili_user;")
            task_ls = [item['user_id'] for item in result_row]
        else:
            task_ls = config.BILI_SPECIFIED_USER_ID_LIST

        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)

        for user_id in task_ls:
            async for gen in self.get_video_list_by_user_id_task(user_id=user_id, semaphore=semaphore):
                for video_item in gen['list']['vlist']:
                    await bilibili_store.update_bilibili_video_by_user_id(video_item)

    async def get_userinfo_by_user_id(self):
        pass
        # async_db_conn: AsyncMysqlDB = media_crawler_db_var.get()
        # result_row: List[Dict[str, Any]] = await async_db_conn.query("SELECT user_id FROM tb_bilibili_user;")
        # return result_row

    async def create_bilibili_client(self, httpx_proxy: Optional[str]) -> BilibiliClient:
        """Create xhs client"""
        utils.logger.info("[BilibiliCrawler.create_bilibili_client] Begin create bilibili API client ...")
        cookie_str, cookie_dict = utils.convert_cookies(await self.browser_context.cookies())
        bilibili_client_obj = BilibiliClient(
            proxies=httpx_proxy,
            headers={
                "User-Agent": self.user_agent,
                "Cookie": cookie_str,
                "Origin": "https://www.bilibili.com",
                "Referer": "https://www.bilibili.com",
                "Content-Type": "application/json;charset=UTF-8"
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
        )
        return bilibili_client_obj

    @staticmethod
    def format_proxy_info(ip_proxy_info: IpInfoModel) -> Tuple[Optional[Dict], Optional[Dict]]:
        """format proxy info for playwright and httpx"""
        playwright_proxy = {
            "server": f"{ip_proxy_info.protocol}{ip_proxy_info.ip}:{ip_proxy_info.port}",
            "username": ip_proxy_info.user,
            "password": ip_proxy_info.password,
        }
        httpx_proxy = {
            f"{ip_proxy_info.protocol}": f"http://{ip_proxy_info.user}:{ip_proxy_info.password}@{ip_proxy_info.ip}:{ip_proxy_info.port}"
        }
        return playwright_proxy, httpx_proxy

    async def launch_browser(
            self,
            chromium: BrowserType,
            playwright_proxy: Optional[Dict],
            user_agent: Optional[str],
            headless: bool = True
    ) -> BrowserContext:
        """Launch browser and create browser context"""
        utils.logger.info("[BilibiliCrawler.launch_browser] Begin create browser context ...")
        if config.SAVE_LOGIN_STATE:
            # feat issue #14
            # we will save login state to avoid login every time
            user_data_dir = os.path.join(os.getcwd(), "browser_data",
                                         config.USER_DATA_DIR % self.platform)  # type: ignore
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,  # type: ignore
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent
            )
            return browser_context
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy)  # type: ignore
            browser_context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent
            )
            return browser_context
