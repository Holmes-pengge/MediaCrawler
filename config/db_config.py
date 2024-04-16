import os

# redis config
REDIS_DB_HOST = "127.0.0.1"  # your redis host
REDIS_DB_PWD = os.getenv("REDIS_DB_PWD", "123456")  # your redis password

# mysql config
RELATION_DB_PWD = os.getenv("RELATION_DB_PWD", "mysqlroot")  # your relation db password
# RELATION_DB_URL = f"mysql://root:{RELATION_DB_PWD}@114.132.121.10:4307/bigdata"
RELATION_DB_URL = f"mysql://root:mysqlroot@192.168.0.241:4307/bigdata"

# sqlite3 config
# RELATION_DB_URL = f"sqlite://data/media_crawler.sqlite"
