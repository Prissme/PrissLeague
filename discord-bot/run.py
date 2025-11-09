#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Entry point for the Discord ELO Bot
Run this file to start the bot
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the main function
from main import main

if __name__ == '__main__':
    # Check required environment variables
    if not os.getenv('DISCORD_TOKEN'):
        print("❌ DISCORD_TOKEN environment variable is missing!")
        print("Please set it in your .env file or environment")
        sys.exit(1)
    
    if not os.getenv('DATABASE_URL'):
        print("❌ DATABASE_URL environment variable is missing!")
        print("Please set it in your .env file or environment")
        sys.exit(1)
    
    print("🚀 Starting Discord ELO Bot...")
    
    try:
        # Run the bot
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
