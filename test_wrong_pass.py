#!/usr/bin/env python3
import asyncio
import asyncpg

async def main():
    print("Connecting with wrong password...")
    try:
        conn = await asyncpg.connect(
            host='localhost', port=5432, user='postgres',
            password='wrong', database='stock_data_test'
        )
        print("Connected")
    except Exception as e:
        print(f"Error: {e}")
        return
    print("Success")

if __name__ == "__main__":
    asyncio.run(main())