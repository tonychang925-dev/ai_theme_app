#!/usr/bin/env python3
import asyncio
import asyncpg

async def main():
    print("Connecting...")
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='postgres',
        password='postgres', database='stock_data_test'
    )
    print("Connected")
    rows = await conn.fetch("SELECT 1")
    print(f"Result: {rows}")
    await conn.close()
    print("Closed")

if __name__ == "__main__":
    asyncio.run(main())