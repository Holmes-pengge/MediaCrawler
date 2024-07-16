import os

IS_PRODUCTION = True
# mysql config
# RELATION_DB_PWD = os.getenv("RELATION_DB_PWD", "123456")
# RELATION_DB_USER = os.getenv("RELATION_DB_USER", "root")
# RELATION_DB_HOST = os.getenv("RELATION_DB_HOST", "localhost")
# RELATION_DB_PORT = os.getenv("RELATION_DB_PORT", "3306")
# RELATION_DB_NAME = os.getenv("RELATION_DB_NAME", "media_crawler")

# RELATION_DB_URL = f"mysql://{RELATION_DB_USER}:{RELATION_DB_PWD}@{RELATION_DB_HOST}:{RELATION_DB_PORT}/{RELATION_DB_NAME}"
# mysql config
# RELATION_DB_PWD = os.getenv("RELATION_DB_PWD", "mysqlroot")  # your relation db password
# RELATION_DB_URL = f"mysql://root:{RELATION_DB_PWD}@114.132.121.10:4307/bigdata"
# RELATION_DB_URL = f"mysql://root:{RELATION_DB_PWD}@192.168.11.241:4307/spider"
# RELATION_DB_URL = f"mysql://root:Tech%232024%40CP@gz-cdb-730keikn.sql.tencentcdb.com:57078/spider" if IS_PRODUCTION else f"mysql://root:mysqlroot@192.168.11.241:4307/spider"
RELATION_DB_URL = "mysql://root:mysqlroot@192.168.11.241:4307/bigdata"

# redis config
REDIS_DB_HOST = "127.0.0.1"  # your redis host
REDIS_DB_PWD = os.getenv("REDIS_DB_PWD", "123456")  # your redis password
REDIS_DB_PORT = os.getenv("REDIS_DB_PORT", 6379)  # your redis port
REDIS_DB_NUM = os.getenv("REDIS_DB_NUM", 0)  # your redis db num

# cache type
CACHE_TYPE_REDIS = "redis"
CACHE_TYPE_MEMORY = "memory"
