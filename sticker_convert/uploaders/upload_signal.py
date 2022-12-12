#!/usr/bin/python
import os
import anyio
from signalstickers_client import StickersClient
from signalstickers_client.models import LocalStickerPack, Sticker
from utils.metadata_handler import MetadataHandler
from utils.sticker_convert import StickerConvert
from utils.format_verify import FormatVerify
from utils.exceptions import NoTokenException
import tempfile

class UploadSignal:
    @staticmethod
    async def upload_stickers_signal_async(uuid, password, in_dir, title=None, author=None, res_max=512, res_min=256, quality_max=90, quality_min=0, fps_max=30, fps_min=3, color_max=90, color_min=60, steps=20, default_emoji='😀', **kwargs):
        urls = []     
        title, author, emoji_dict = MetadataHandler.get_metadata(in_dir, title=title, author=author)
        packs = MetadataHandler.split_sticker_packs(in_dir, title=title, file_per_pack=200, separate_image_anim=False)

        if title == None:
            raise TypeError(f'title cannot be {title}')
        if author == None:
            raise TypeError(f'author cannot be {author}')
        if emoji_dict == None:
            print('emoji.txt is required for uploading signal stickers')
            print(f'emoji.txt generated for you in {in_dir}')
            print(f'Default emoji is set to {default_emoji}. If you just want to use this emoji on all stickers in this pack, run script again')
            MetadataHandler.generate_emoji_file(dir=in_dir, default_emoji=default_emoji)
            return ['emoji.txt is required for uploading signal stickers', f'emoji.txt generated for you in {in_dir}', f'Default emoji is set to {default_emoji}. If you just want to use this emoji on all stickers in this pack, run script again']
        
        for pack_title, stickers in packs.items():
            pack = LocalStickerPack()
            pack.author = author
            pack.title = pack_title

            with tempfile.TemporaryDirectory() as tempdir:
                for src in stickers:
                    print('Verifying', src, 'for uploading to signal')

                    src_full_name = os.path.split(src)[-1]
                    src_name = os.path.splitext(src_full_name)[0]
                    
                    if not (FormatVerify.check_file(src, square=True, size_max=300000, animated=True, format='.apng') or
                            FormatVerify.check_file(src, square=True, size_max=300000, animated=False, format='.png') or
                            FormatVerify.check_file(src, square=True, size_max=300000, animated=False, format='.webp')):

                        if FormatVerify.is_anim(src):
                            extension = '.apng'
                        else:
                            extension = '.png'
                            
                        sticker_path = os.path.join(tempdir, src_name + extension)
                        StickerConvert.convert_and_compress_to_size(src, sticker_path, vid_size_max=300000, img_size_max=300000, res_min=res_min, res_max=res_max, quality_max=quality_max, quality_min=quality_min, fps_max=fps_max, fps_min=fps_min, color_min=color_min, color_max=color_max, steps=steps)
                    else:
                        sticker_path = src

                    sticker = Sticker()
                    sticker.id = pack.nb_stickers

                    try:
                        sticker.emoji = emoji_dict[src_name][:1]
                    except KeyError:
                        print(f'Warning: Cannot find emoji for file {src_full_name}, skip uploading this file...')
                        continue

                    with open(sticker_path, "rb") as f_in:
                        sticker.image_data = f_in.read()

                    pack._addsticker(sticker)

            async with StickersClient(uuid, password) as client:
                pack_id, pack_key = await client.upload_pack(pack)
            
            print(f"https://signal.art/addstickers/#pack_id={pack_id}&pack_key={pack_key}")
            urls.append(f"https://signal.art/addstickers/#pack_id={pack_id}&pack_key={pack_key}")
        
        return urls

    @staticmethod
    def upload_stickers_signal(uuid, password, in_dir, title=None, author=None, res_max=512, res_min=256, quality_max=90, quality_min=0, fps_max=30, fps_min=3, color_max=90, color_min=60, steps=20, default_emoji='😀', **kwargs):
        if uuid == None:
            raise NoTokenException('uuid required for uploading to signal')
        if password == None:
            raise NoTokenException('password required for uploading to signal')

        return anyio.run(UploadSignal.upload_stickers_signal_async, uuid, password, in_dir, title, author, res_max, res_min, quality_max, quality_min, fps_max, fps_min, color_max, color_min, steps, default_emoji)