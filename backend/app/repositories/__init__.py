"""仓储层包

仓储（Repository）是唯一直接操作 SQLAlchemy Session 的地方，
服务层通过仓储读写数据，不再散落地写 db.query(...)。
"""
