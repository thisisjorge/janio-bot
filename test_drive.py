import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from janio_bot.services.drive_service import drive_vault_service

async def main():
    drive_vault_service.start()
    await asyncio.sleep(2) # let it init
    
    print(f"Folder ID: {drive_vault_service.folder_id}")
    
    video_id = "nIPGdv-vkSY"
    print(f"Searching for {video_id}...")
    
    items = await drive_vault_service.list_vault()
    print(f"Items in vault: {len(items)}")
    for item in items:
        print(item)
        
    local_path = await drive_vault_service.search_by_video_id(video_id)
    print(f"Local path: {local_path}")

if __name__ == "__main__":
    asyncio.run(main())
