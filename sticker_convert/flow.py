#!/usr/bin/env python3
import os
import shutil
import time
from datetime import datetime
from threading import Thread

from downloaders.download_line import DownloadLine
from downloaders.download_signal import DownloadSignal
from downloaders.download_telegram import DownloadTelegram
from downloaders.download_kakao import DownloadKakao

from uploaders.upload_signal import UploadSignal
from uploaders.upload_telegram import UploadTelegram
from uploaders.compress_wastickers import CompressWastickers
from uploaders.xcode_imessage import XcodeImessage

from utils.converter import StickerConvert
from utils.codec_info import CodecInfo
from utils.curr_dir import CurrDir

class Flow:
    def __init__(self,
        opt_input, opt_comp, opt_output, opt_cred, 
        input_presets, output_presets, cb_msg, cb_msg_block, cb_bar, cb_ask_bool):

        self.opt_input = opt_input
        self.opt_comp = opt_comp
        self.opt_output = opt_output
        self.opt_cred = opt_cred
        self.input_presets = input_presets
        self.output_presets = output_presets
        self.cb_msg = cb_msg
        self.cb_msg_block = cb_msg_block
        self.cb_bar = cb_bar
        self.cb_ask_bool = cb_ask_bool

        self.compress_fails = []
        self.out_urls = []

        if self.opt_input['dir'] == None:
            self.opt_input['dir'] = os.path.join(CurrDir.get_curr_dir(), 'stickers_input')

        if self.opt_output['dir'] == None:
            self.opt_output['dir'] = os.path.join(CurrDir.get_curr_dir(), 'stickers_output')

        if os.path.isdir(self.opt_input['dir']) == False:
            os.makedirs(self.opt_input['dir'])

        if os.path.isdir(self.opt_output['dir']) == False:
            os.makedirs(self.opt_output['dir'])

    def start(self):
        self.cb_bar(set_progress_mode='indeterminate')
        self.cb_msg(cls=True)

        tasks = (
            self.sanitize,
            self.verify_input,
            self.cleanup,
            self.download,
            self.compress,
            self.export,
            self.report
        )

        for task in tasks:
            success = task()
            if not success:
                return False

        return True
    
    def sanitize(self):
        def to_int(i):
            return i if i != None else None

        try:
            self.opt_comp['size_max']['img'] = to_int(self.opt_comp['size_max']['img'])
            self.opt_comp['size_max']['vid'] = to_int(self.opt_comp['size_max']['vid'])
            self.opt_comp['fps']['min'] = to_int(self.opt_comp['fps']['min'])
            self.opt_comp['fps']['max'] = to_int(self.opt_comp['fps']['max'])
            self.opt_comp['res']['w']['min'] = to_int(self.opt_comp['res']['w']['min'])
            self.opt_comp['res']['w']['max'] = to_int(self.opt_comp['res']['w']['max'])
            self.opt_comp['res']['h']['min'] = to_int(self.opt_comp['res']['h']['min'])
            self.opt_comp['res']['h']['max'] = to_int(self.opt_comp['res']['h']['max'])
            self.opt_comp['quality']['min'] = to_int(self.opt_comp['quality']['min'])
            self.opt_comp['quality']['max'] = to_int(self.opt_comp['quality']['max'])
            self.opt_comp['color']['min'] = to_int(self.opt_comp['color']['min'])
            self.opt_comp['color']['max'] = to_int(self.opt_comp['color']['max'])
            self.opt_comp['duration']['min'] = to_int(self.opt_comp['duration']['min'])
            self.opt_comp['duration']['max'] = to_int(self.opt_comp['duration']['max'])
            self.opt_comp['steps'] = to_int(self.opt_comp['steps'])
            self.opt_comp['processes'] = to_int(self.opt_comp['processes'])
        except ValueError:
            self.cb_msg('Non-numbers found in field(s). Check your input and try again.')
            return False

        return True

    def verify_input(self):
        msg = ''

        save_to_local_tip = ''
        save_to_local_tip += '    If you want to upload the results by yourself,\n'
        save_to_local_tip += '    select "Save to local directory only" for output\n'

        if (self.opt_input['option'] != 'local' and 
            not self.opt_input.get('url')):

            msg += '\n'
            msg += '[X] URL address cannot be empty.\n'
            msg += '    If you only want to use local files,\n'
            msg += '    choose "Save to local directory only"\n'
            msg += '    in "Input source"\n'
        

        if ((self.opt_input.get('option') == 'telegram' or 
            self.opt_output.get('option') == 'telegram') and 
            not self.opt_cred.get('telegram', {}).get('token')):

            msg += '[X] Downloading from and uploading to telegram requires bot token.\n'
            msg += save_to_local_tip

        if (self.opt_output.get('option') == 'telegram' and 
            not self.opt_cred.get('telegram', {}).get('userid')):

            msg += '[X] Uploading to telegram requires user_id \n'
            msg += '    (From real account, not bot account).\n'
            msg += save_to_local_tip
        

        if (self.opt_output.get('option') == 'signal' and 
            not (self.opt_cred.get('signal', {}).get('uuid') and self.opt_cred.get('signal', {}).get('password'))):

            msg += '[X] Uploading to signal requires uuid and password.\n'
            msg += save_to_local_tip
        

        if (self.opt_output.get('option') == 'telegram' and 
            not self.opt_output.get('title')):

            msg += '[X] Uploading to telegram requires title\n'

        
        if (self.opt_output.get('option') == 'signal' and 
            not (self.opt_output.get('title') and self.opt_output.get('author'))):

            msg += '[X] Uploading to signal requires title and author\n'
        

        if (self.opt_output.get('option') == 'whatsapp' and 
            not (self.opt_output.get('title') and self.opt_output.get('author'))):

            msg += '[X] Compressing to .wastickers requires title and author\n'
        

        if (self.opt_output.get('option') == 'imessage' and 
            not (self.opt_output.get('title') and self.opt_output.get('author'))):

            msg += '[X] Creating Xcode project (for iMessage) requires title and author\n'
        

        if msg != '':
            self.cb_msg(msg)
            return False
        
        # Check if preset not equal to export option
        # Only warn if the compression option is available in export preset
        # Only warn if export option is not local or custom
        # Do not warn if no_compress is true
        if (not self.opt_comp['no_compress'] and 
            self.opt_output['option'] not in ('local', 'custom') and
            self.opt_comp['preset'] != self.opt_output['option'] and 
            self.opt_comp['preset'] in self.output_presets):

            msg = 'Compression preset does not match export option\n'
            msg += 'You may continue, but the files will need to be compressed again before export\n'
            msg += 'You are recommended to choose the matching option for compression and output. Continue?'

            response = self.cb_ask_bool(msg)

            if response == False:
                return False
        
        # Warn about unable to download animated Kakao stickers with such link
        if (self.opt_output.get('option') == 'kakao' and 
            'e.kakao.com' in self.opt_input.get('url') and
            not self.opt_cred.get('kakao', {}).get('auth_token')):

            msg = 'To download ANIMATED stickers from e.kakao.com,\n'
            msg += 'you need to generate auth_token.\n'
            msg += 'Alternatively, you can generate share link (emoticon.kakao.com/items/xxxxx)\n'
            msg += 'from Kakao app on phone.\n'
            msg += 'You are adviced to read documentations.\n'
            msg += 'If you continue, you will only download static stickers. Continue?'

            response = self.cb_ask_bool(msg)

            if response == False:
                return False
        
        # Warn about telegram_vector compression preset.
        if self.opt_comp['format']['img'] == '.tgs' or self.opt_comp['format']['vid'] == '.tgs':
            msg = 'Warning: You should not convert bitmap to .tgs\n'
            msg += 'If you want to create telegram stickers, choose `telegram` instead of `telegram_vector` for compression preset.\n'
            msg += 'If you continue, it will likely fail unless you know what you are doing. Continue?'
            
            response = self.cb_ask_bool(msg)

            if response == False:
                return False
        
        return True

    def cleanup(self):
        # If input is 'From local directory', then we should keep files in input/output directory as it maybe edited by user
        # If input is not 'From local directory', then we should move files in input/output directory as new files will be downloaded
        # Output directory should be cleanup unless no_compress is true (meaning files in output directory might be edited by user)

        timestamp = datetime.now().strftime('%Y-%d-%m_%H-%M-%S')
        dir_name = 'archive_' + timestamp

        in_dir_files = [i for i in os.listdir(self.opt_input['dir']) if not i.startswith('archive_')]
        out_dir_files = [i for i in os.listdir(self.opt_output['dir']) if not i.startswith('archive_')]

        if self.opt_input['option'] == 'local':
            self.cb_msg('Skip moving old files in input directory as input source is local')
        elif len(in_dir_files) == 0:
            self.cb_msg('Skip moving old files in input directory as input source is empty')
        else:
            archive_dir = os.path.join(self.opt_input['dir'], dir_name)
            self.cb_msg(f"Moving old files in input directory to {archive_dir} as input source is not local")
            os.makedirs(archive_dir)
            for i in in_dir_files:
                old_path = os.path.join(self.opt_input['dir'], i)
                new_path = os.path.join(archive_dir, i)
                shutil.move(old_path, new_path)

        if self.opt_comp['no_compress']:
            self.cb_msg('Skip moving old files in output directory as no_compress is True')
        elif len(out_dir_files) == 0:
            self.cb_msg('Skip moving old files in output directory as output source is empty')
        else:
            archive_dir = os.path.join(self.opt_output['dir'], dir_name)
            self.cb_msg(f"Moving old files in output directory to {archive_dir}")
            os.makedirs(archive_dir)
            for i in out_dir_files:
                old_path = os.path.join(self.opt_output['dir'], i)
                new_path = os.path.join(archive_dir, i)
                shutil.move(old_path, new_path)
        
        return True

    def download(self):
        downloaders = []

        if self.opt_input['option'] == 'signal':
            downloaders.append(DownloadSignal.download_stickers_signal)

        if self.opt_input['option'] == 'line':
            downloaders.append(DownloadLine.download_stickers_line)
            
        if self.opt_input['option'] == 'telegram':
            downloaders.append(DownloadTelegram.download_stickers_telegram)

        if self.opt_input['option'] == 'kakao':
            downloaders.append(DownloadKakao.download_stickers_kakao)
        
        if len(downloaders) > 0:
            self.cb_msg('Downloading...')
        else:
            self.cb_msg('Nothing to download')
            return True
        
        for downloader in downloaders:
            success = downloader(
                url=self.opt_input['url'], 
                out_dir=self.opt_input['dir'], 
                opt_cred=self.opt_cred,
                cb_msg=self.cb_msg, cb_msg_block=self.cb_msg_block, cb_bar=self.cb_bar)
            self.cb_bar(set_progress_mode='indeterminate')
            if success == False:
                return False

        return True

    def compress(self):
        if self.opt_comp['no_compress'] == True:
            self.cb_msg('no_compress is set to True, skip compression')
            in_dir_files = [i for i in os.listdir(self.opt_input['dir']) if os.path.isfile(os.path.join(self.opt_input['dir'], i))]
            out_dir_files = [i for i in os.listdir(self.opt_output['dir']) if os.path.isfile(os.path.join(self.opt_output['dir'], i))]
            if len(in_dir_files) == 0:
                self.cb_msg('Input directory is empty, nothing to copy to output directory')
            elif len(out_dir_files) != 0:
                self.cb_msg('Output directory is not empty, not copying files from input directory')
            else:
                self.cb_msg('Output directory is empty, copying files from input directory')
                for i in in_dir_files:
                    src_f = os.path.join(self.opt_input['dir'], i)
                    dst_f = os.path.join(self.opt_output['dir'], i)
                    shutil.copy(src_f, dst_f)
            return True
        msg = 'Compressing...'

        input_dir = self.opt_input['dir']
        output_dir = self.opt_output['dir']

        if self.opt_comp['format']['vid'] == '.png' or self.opt_comp['format']['vid'] == '.apng':
            msg += '\nTips: Compressing .apng takes long time.'
            msg += '\nConsider using another format or lowering "--steps"'
        
        in_fs = []

        # .txt: emoji.txt, title.txt
        # .m4a: line sticker sound effects
        for i in os.listdir(input_dir):
            in_f = os.path.join(input_dir, i)
            
            if not os.path.isfile(in_f):
                continue
            elif CodecInfo.get_file_ext(i) in ('.txt', '.m4a'):
                shutil.copy(in_f, os.path.join(output_dir, i))
            else:
                in_fs.append(i)

        in_fs_count = len(in_fs)

        self.cb_msg(msg)
        self.cb_bar(set_progress_mode='determinate', steps=in_fs_count)
        
        threads = []
        for i in in_fs:
            in_f = os.path.join(input_dir, i)

            if CodecInfo.is_anim(in_f) or self.opt_comp['fake_vid']:
                extension = self.opt_comp['format']['vid']
            else:
                extension = self.opt_comp['format']['img']

            out_f = os.path.join(output_dir, os.path.splitext(i)[0] + extension)

            thread = Thread(
                    target=self.compress_thread, 
                    args=(in_f, out_f, self.opt_comp),
                    daemon=True
                    )

            threads.append(thread)
        
            while True:
                if sum((t.is_alive() for t in threads)) < self.opt_comp['processes']:
                    thread.start()
                    break
                else:
                    time.sleep(1)

        for thread in threads:
            thread.join()

        return True
    
    def compress_thread(self, in_f, out_f, opt_comp):
        result = StickerConvert.convert_and_compress_to_size(in_f, out_f, opt_comp, self.cb_msg)
        if result == False:
            self.compress_fails.append(in_f)

        self.cb_bar(update_bar=True)

    def export(self):
        self.cb_msg('Exporting...')
        self.cb_bar(set_progress_mode='indeterminate')

        exporters = []

        if self.opt_output['option'] == 'whatsapp':
            exporters.append(CompressWastickers.compress_wastickers)

        if self.opt_output['option'] == 'signal':
            exporters.append(UploadSignal.upload_stickers_signal)

        if self.opt_output['option'] == 'telegram':
            exporters.append(UploadTelegram.upload_stickers_telegram)

        if self.opt_output['option'] == 'imessage':
            exporters.append(XcodeImessage.create_imessage_xcode)
        
        for exporter in exporters:
            self.out_urls += exporter(
                opt_output=self.opt_output, opt_comp=self.opt_comp, opt_cred=self.opt_cred, 
                cb_msg=self.cb_msg, cb_msg_block=self.cb_msg_block, cb_bar=self.cb_bar)
        
        if self.out_urls != []:
            with open(os.path.join(self.opt_output['dir'], 'export-result.txt'), 'w+') as f:
                f.writelines(self.out_urls)
                
        return True
    
    def report(self):
        msg = '##########\n'
        msg += 'Summary:\n'
        msg += '##########\n'
        msg += '\n'

        if self.compress_fails != []:
            msg += f'Warning: The following {len(self.compress_fails)} file{"s" if len(self.compress_fails) > 1 else ""} compression failed:\n'
            msg += "\n".join(self.compress_fails)
            msg += '\n'

        if self.out_urls != []:
            msg += 'Export results:\n'
            msg += '\n'.join(self.out_urls)
        else:
            msg += 'Export result: None'

        self.cb_msg(msg)

        return True