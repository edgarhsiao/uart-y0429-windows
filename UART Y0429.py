import os
import glob
import sys
import logging
import tkinter as tk
import serial
import serial.tools.list_ports
import struct
import subprocess
from tkinter import ttk
from tkinter import scrolledtext
from tkinter import filedialog
import threading
import time
import hashlib
import binascii
from io import StringIO
import shlex
import zipfile
import socket
import multiprocessing as mp

os_name = os.name


SW_Ver = 'Y0429'

log = logging.getLogger('info_log')
log.setLevel(logging.DEBUG)

log_format = logging.Formatter('%(filename)s %(funcName)s %(asctime)s %(message)s')
shw_format = logging.Formatter('%(message)s')

ticks = str(int(time.time()))
py_fn = os.path.basename(__file__).split('.')[0]
# ticks = str(int(time.time()))
# fh = logging.FileHandler("%s_%s.log" % (py_fn, ticks), mode='w')
fh = logging.FileHandler("%s.log" % (py_fn), mode='w')
sh = logging.StreamHandler()

fh.setFormatter(log_format)
sh.setFormatter(shw_format)

log.addHandler(fh)
log.addHandler(sh)

#----------------------------------------------------------------------------------------------------------------------
#-- For Function Setting

#----------------------------------------------------------------------------------------------------------------------
class parsing_mp(object):
    def __init__(self, cmd_qu, rep_qu, log_f, en_systime_chk, rec_buf_size):
        self.cmd_qu = cmd_qu
        self.rep_qu = rep_qu
        self.log_f = log_f
        self.en_systime_chk = en_systime_chk
        self.rec_buf_size = rec_buf_size
        self.process = None
        # self.mp_is_valid = 0
    
    def __delete__(self):
        self.stop()
    
    def start(self):
        # self.stop()
        # self.process = mp.Process(target=self.parsing_run, args=(self.cmd_qu, self.rep_qu, self.tag, self.tag2, 
        #     self.tag_num, self.content, self.en_systime_chk, 0x800000, ))
        self.process = mp.Process(target=self.parsing_run, args=(self.cmd_qu, self.rep_qu, self.log_f, 
            self.en_systime_chk, self.rec_buf_size, ))
        self.process.daemon = True
        self.process.start()
        # self.mp_is_valid = 1

    def stop(self):
        if self.process:
            self.process.join(1)
            self.process = None
    
    # def parsing_run(self, cmd_qu, rep_qu, tag, tag2, tag_num, content, en_systime_chk, rec_buf_size):
    def parsing_run(self, cmd_qu, rep_qu, log_f, en_systime_chk, rec_buf_size):
        rec_w_ptr = 0
        rec_r_ptr = 0
        rec_remain = 0
        # rec_buf = bytearray(rec_buf_size)
        # rec_buf = bytearray(0)
        rec_buf = bytes()
        err_cnt = 0
        err_buf_size = 0x10000      # 0x10000 = 64K
        # err_buf = bytearray(err_buf_size)
        err_buf = bytes()
        rec_start = 1
        log_size = 0
        log_end = 0
        
        ticks_s = int(time.time())
        log.debug("event_parsing data.")
        parsing = event_parsing(log_f)
        tag = parsing.tag
        tag2 = parsing.tag2
        tag_num = parsing.tag_num
        content = parsing.content
        
        rep_qu.put(0)
        while rec_start:
            size, data = cmd_qu.get()
            rec_remain = rec_w_ptr + size
            if size==0:
                log.debug("Stop")
                rep_qu.put([rec_remain, "Stop", 'red', rec_buf[0:rec_remain]])
                break
            
            # if rec_remain>rec_buf_size:
            #     log.debug("Receive too much data.")
            #     break
            # rec_buf[rec_w_ptr:rec_remain] = bytearray(data)
            rec_buf = rec_buf + data
            rec_w_ptr = rec_remain
            rec_r_ptr = 0
            
            while rec_remain:
                if rec_remain < 2:
                    # rec_buf[0:rec_remain] = rec_buf[rec_r_ptr:rec_w_ptr]
                    rec_buf = rec_buf[rec_r_ptr:rec_w_ptr]
                    rec_w_ptr = rec_remain
                    break
                
                rec_r_end = rec_r_ptr + 2
                try:
                    log_idx = tag.index(rec_buf[rec_r_ptr:rec_r_end])
                except:
                    # err_buf[err_cnt] = rec_buf[rec_r_ptr]
                    # log.debug(err_buf)
                    # log.debug(rec_buf[rec_r_ptr])
                    err_buf = err_buf[0:err_cnt] + rec_buf[rec_r_ptr:(rec_r_ptr+1)]
                    err_cnt += 1
                    rec_r_ptr += 1
                    rec_remain -= 1
                    continue
                
                #-- SATA only -----------------------------------------------------------------------------------------
                if (content[log_idx][1]>2) or (len(tag_num[log_idx])>1):  
                    find_tag = 0
                    for tag_lp in range(0, len(tag_num[log_idx])):
                        rec_r_end = rec_r_ptr +  tag_num[log_idx][tag_lp]
                        try:
                            log_idx = tag2.index(rec_buf[rec_r_ptr:rec_r_end], log_idx)
                            find_tag = 1
                            break
                        except:
                            continue
                    
                    if find_tag==0:
                        # err_buf[err_cnt] = rec_buf[rec_r_ptr]
                        # err_buf = err_buf + rec_buf[rec_r_ptr]
                        err_buf = err_buf[0:err_cnt] + rec_buf[rec_r_ptr:(rec_r_ptr+1)]
                        err_cnt += 1
                        rec_r_ptr += 1
                        rec_remain -= 1
                        continue
                
                #------------------------------------------------------------------------------------------------------
                if err_cnt:
                    show_err = ''
                    if err_cnt>err_buf_size:
                        log.debug("Too Much Error Data")
                        rec_start = 0
                        break
                    for lp in range(0, err_cnt):
                        show_err = show_err + ("%02x " % err_buf[lp])
                    show_err = show_err + '\n'
                    rep_qu.put([err_cnt, show_err, 'red', err_buf])
                    err_buf = bytes()
                    # rep_qu.put([err_cnt, show_err, 0, 0])
                    err_cnt = 0
                
                log_size = content[log_idx][8]
                if log_size > rec_remain:
                    # rec_buf[0:rec_remain] = rec_buf[rec_r_ptr:rec_w_ptr]
                    rec_buf = rec_buf[rec_r_ptr:rec_w_ptr]
                    rec_w_ptr = rec_remain
                    break
                
                log_end = rec_r_end + content[log_idx][5]
                try:
                    show_tuple = content[log_idx][7].unpack(rec_buf[rec_r_end:log_end])
                except:
                    log.debug("rec_r_end = %d  log_end = %d" % (rec_r_end, log_end))
                    log.debug(content[log_idx][2])
                    log.debug(content[log_idx][5])
                    log.debug(content[log_idx][6])
                    log.debug("Please Check LogSetting.dat file")
                    rec_start = 0
                    break
                
                #[U0830][Wade] Add system timestamp
                if content[log_idx][4]:
                    try:
                        show = (content[log_idx][2] % show_tuple) + "\n"
                    except:
                        log.debug("error string = %s" % content[log_idx][2])
                        log.debug(show_tuple)
                        rec_start = 0
                        break
                else:
                    show = content[log_idx][2] + "\n"
                
                if en_systime_chk:
                    sysTimestamp = time.localtime()
                    current_time = time.strftime("***%Y/%m/%d_%H-%M-%S***", sysTimestamp)
                    show = current_time + show
                
                rep_qu.put([log_size, show, content[log_idx][3], rec_buf[rec_r_ptr:log_end]])
                # rep_qu.put([log_size, show, 0, 0])
                rec_r_ptr = log_end
                rec_remain -= log_size
        
        # self.mp_is_valid = 0
        log.debug('parsing run = %d' % (int(time.time())-ticks_s))
    
    
#----------------------------------------------------------------------------------------------------------------------
#-- clase py_window
class py_window(tk.Frame):
    def __init__(self, master=None, ModSel=0):
        tk.Frame.__init__(self, master)
        self.log_open = 0
        self.parsing = []
        self.rec_start = 0
        self.rec_th_fg = 0
        self.com_sel = ''
        self.max_f_size = (10 * 1024 * 1024) - 128  # bin file max size
        self.pos = 0.0
        self.debug = 0                              # debug receive error.  If enable parsing file will write debug information
        self.LEDSize = 30
        self.LEDStart = 2
        self.ModSel = ModSel
        self.en_mp = 1
        
        if os_name == "nt":
            self.LogSettingPath = r".\LogSetting.dat"
            self.store_fd = ".\\Store\\"
            self.bin_fd = "\\Bin\\"
            self.txt_fd = "\\Txt\\"
            self.max_buf = 32768
            self.show_limit = 20    # = 1,048,576
        else:
            self.LogSettingPath = "./LogSetting.dat"
            self.store_fd = "./Store/"
            self.bin_fd = "/Bin/"
            self.txt_fd = "/Txt/"
            self.max_buf = 2048
            self.show_limit = 12    # = 4096
        
        self.create_widgets()
        
        
    def create_widgets(self):
        self.rec = uart()
        
        self.master.title("FW Debug %s %s" % (SW_Ver, os.getcwd()))
        self.master.geometry("852x620+200+60")
        
        if self.ModSel==2:
            self.tab_ctl = ttk.Notebook(self.master)
            self.uart_tab = tk.Frame(self.tab_ctl)
            self.tab_ctl.add(self.uart_tab, text='UART')
            
            self.uart_pack = self.uart_tab
            self.tab_ctl.pack(expand=1, fill="both")
        else:
            self.uart_pack = self.master
        
        self.text = scrolledtext.ScrolledText(self.uart_pack, height=36, width=80, wrap=tk.NONE)
        self.text.place(x=0, y=0, height=580, width=640)
        self.text.config(state="disabled")
        self.text.tag_config('red', foreground = 'red')
        self.text.tag_config('green', foreground = 'green')
        self.text.tag_config('blue', foreground = 'blue')
        self.text.tag_config('yellow', foreground = 'yellow')
        self.text.tag_config('black', foreground = 'black')
        
        self.xscrol = tk.Scrollbar(self.uart_pack, orient=tk.HORIZONTAL, command=self.text.xview)
        self.xscrol.place(x=0, y=580, width=640)
        self.text['xscrollcommand'] = self.xscrol.set
        
        if os.name == "posix":
            self.StartBut = tk.Button(self.uart_pack, text='Start', width=6, height=1, command=self.StartBut_Click)
            self.StartBut.place(x=730, y=6)
        else:
            self.StartBut = tk.Button(self.uart_pack, text='Start', width=7, height=1, command=self.StartBut_Click)
            self.StartBut.place(x=720, y=6)
        if self.rec.cp210x_cnt==0:
            self.StartBut.config(state='disabled')
        
        if os.name == "posix":
            self.StopBut = tk.Button(self.uart_pack, text='Stop', width=6, height=1, command=self.StopBut_Click)
        else:
            self.StopBut = tk.Button(self.uart_pack, text='Stop', width=7, height=1, command=self.StopBut_Click)
        self.StopBut.place(x=646, y=6)
        self.StopBut.config(state='disabled')
        
        if os.name == "posix":
            self.OpenBut = tk.Button(self.uart_pack, text='Parse File', width=7, height=1, command=self.OpenBut_Click)
        else:
            self.OpenBut = tk.Button(self.uart_pack, text='Parse File', width=8, height=1, command=self.OpenBut_Click)
        # self.OpenBut.place(x=646, y=134)
        self.OpenBut.place(x=646, y=180)
        
        if os.name == "posix":
            self.FolderBut = tk.Button(self.uart_pack, text='Parse Folder', width=7, height=1, command=self.FolderBut_Click)
        else:
            self.FolderBut = tk.Button(self.uart_pack, text='Parse Folder', width=8, height=1, command=self.FolderBut_Click)
        # self.FolderBut.place(x=646, y=166)
        self.FolderBut.place(x=740, y=180)
        
        self.color_var = tk.IntVar(value=1)
        self.color_chk = 1
        self.color_but = tk.Checkbutton(self.uart_pack, text='Color',variable=self.color_var, onvalue=1, offvalue=0, command=self.color_but_sel)
        self.color_but.place(x=644, y=214)
        
        self.all_var = tk.IntVar(value=1)
        self.all_chk = 1
        self.all_but = tk.Checkbutton(self.uart_pack, text='All',variable=self.all_var, onvalue=1, offvalue=0, command=self.all_but_sel)
        self.all_but.place(x=704, y=214)
        
        self.en_mp_var = tk.IntVar(value=0)
        self.en_mp_chk = 0
        self.en_mp_but = tk.Checkbutton(self.uart_pack, text='en_mp',variable=self.en_mp_var, onvalue=1, offvalue=0, command=self.en_mp_but_sel)
        self.en_mp_but.place(x=740, y=214)
        
        self.del_txt_var = tk.IntVar(value=0)
        self.del_txt_chk = 0
        self.del_txt_but = tk.Checkbutton(self.uart_pack, text='Del Txt',variable=self.del_txt_var, onvalue=1, offvalue=0, command=self.del_txt_but)
        self.del_txt_but.place(x=688, y=85)
        
        self.del_bin_var = tk.IntVar(value=0)
        self.del_bin_chk = 0
        self.del_bin_but = tk.Checkbutton(self.uart_pack, text='Del Bin',variable=self.del_bin_var, onvalue=1, offvalue=0, command=self.del_bin_but)
        self.del_bin_but.place(x=768, y=85)
        
        self.dis_show_var = tk.IntVar(value=0)
        self.dis_show_chk = 0
        self.dis_show_but = tk.Checkbutton(self.uart_pack, text='Disable Show',variable=self.dis_show_var, onvalue=1, offvalue=0, command=self.dis_show_but)
        self.dis_show_but.place(x=688, y=105)
        
        #[U0830][Wade] Add system timestamp
        self.en_systime_var = tk.IntVar(value=0)
        self.en_systime_chk = 0
        self.en_systime_but = tk.Checkbutton(self.uart_pack, text='System Time',variable=self.en_systime_var, onvalue=1, offvalue=0, command=self.en_systime_but)
        self.en_systime_but.place(x=688, y=125)
        
        self.SearchCont = tk.StringVar(self.uart_pack)
        if os.name == "posix":
            self.SearchTxt = tk.Entry(self.uart_pack, show=None, textvariable=self.SearchCont, width=22)
        else:
            self.SearchTxt = tk.Entry(self.uart_pack, show=None, textvariable=self.SearchCont, width=30)
        self.SearchTxt.place(x=646, y=238)
        
        if os.name == "posix":
            self.SchNextBut = tk.Button(self.uart_pack, text='Next', width=6, height=1, command=self.SchNextBut_Click)
            self.SchNextBut.place(x=766, y=266)
        else:
            self.SchNextBut = tk.Button(self.uart_pack, text='Next', width=7, height=1, command=self.SchNextBut_Click)
            self.SchNextBut.place(x=772, y=266)
        self.SchNextBut.config(state='disabled')
        
        if os.name == "posix":
            self.SchPrevBut = tk.Button(self.uart_pack, text='Previous', width=6, height=1, command=self.SchPrevBut_Click)
            self.SchPrevBut.place(x=678, y=266)
        else:
            self.SchPrevBut = tk.Button(self.uart_pack, text='Previous', width=7, height=1, command=self.SchPrevBut_Click)
            self.SchPrevBut.place(x=704, y=266)
        self.SchPrevBut.config(state='disabled')
        
        
            
        comvalue=tk.StringVar()
        self.comboxlist=tk.ttk.Combobox(self.uart_pack, textvariable=comvalue)
        com_list = []
        for lp in range(0, self.rec.cp210x_cnt):
            com_list.append(self.rec.cp210x[lp][0])
        if self.rec.cp210x_cnt:
            self.comboxlist["values"]=com_list
            self.com_sel = com_list[0]
        self.comboxlist.place(x=646, y=44)
        self.comboxlist.bind("<<ComboboxSelected>>", self.com_sel_chg)
        if self.rec.cp210x_cnt:
            self.comboxlist.current(0)
        
        #-- UART file size
        self.max_f_size_vl = tk.StringVar(self.uart_pack, value='1')
        self.max_f_size_et = tk.Entry(self.uart_pack, textvariable=self.max_f_size_vl, width=4)
        self.max_f_size_et.place(x=646, y=72)
        #--
        
        self.f_size_label = tk.Label(self.uart_pack, text='BIN File Size Limit (MB)')
        self.f_size_label.place(x=696, y=70)
        
        self.max_f_num_vl = tk.StringVar(self.uart_pack, value='50')
        self.max_f_num_et = tk.Entry(self.uart_pack, textvariable=self.max_f_num_vl, width=4)
        self.max_f_num_et.place(x=646, y=100)
        
        self.label = tk.Label(self.uart_pack, text='0')
        self.label.place(x=646, y=138)
        
        self.file_name = tk.Label(self.uart_pack, text='0')
        self.file_name.place(x=646, y=158)
        
        try:
            with open(self.LogSettingPath) as source:
                log_f = source.read().splitlines()
                self.log_open = 1
                md5_obj = hashlib.md5()
                for line in log_f:
                    md5_obj.update(line.encode("utf-8"))
                self.log_md5 = md5_obj.hexdigest()
        except:
            log.debug("Open LogSetting.dat fail!!")
        
        if self.log_open:
            self.parsing = event_parsing(log_f)
            for lp in range(0, len(self.parsing.color_st)):
                # log.debug(self.parsing.color_st[lp])
                try:
                    self.text.tag_config(self.parsing.color_st[lp], foreground = self.parsing.color_st[lp])
                except:
                    self.parsing.color_st[lp] = "BLACK"
                    self.text.tag_config(self.parsing.color_st[lp], foreground = self.parsing.color_st[lp])
        
        if self.ModSel==2:
            self.rw_tab = tk.Frame(self.tab_ctl)
            self.tab_ctl.add(self.rw_tab, text='ICE')
            
            self.rw_text = scrolledtext.ScrolledText(self.rw_tab, height=36, width=80, wrap=tk.NONE)
            self.rw_text.place(x=0, y=0, height=580, width=640)
            self.rw_text.config(state="disabled")
            
            self.rw_xscrol = tk.Scrollbar(self.rw_tab, orient=tk.HORIZONTAL, command=self.text.xview)
            self.rw_xscrol.place(x=0, y=580, width=640)
            self.rw_text['xscrollcommand'] = self.rw_xscrol.set
            
            ice_thread = threading.Thread(target=self.ice_thread, name='ICE')
            ice_thread.setDaemon(True)
            ice_thread.start()
            self.ice_serve = 1
            
        
    #------------------------------------------------------------------------------------------------------------------
    def StartBut_Click(self):
        if self.log_open==0:
            return
        self.rec_start = 1
        
        if self.en_mp_chk:
            display_th = threading.Thread(target=self.display_th, name='Display')
            display_th.setDaemon(True)
            display_th.start()
        else:
            display_thread = threading.Thread(target=self.display_thread, name='Display')
            display_thread.setDaemon(True)
            display_thread.start()
        
        while self.rec_th_fg==0: None
        self.rec.rec_th_fg = 0
        if self.rec_start:
            self.StartBut.config(state='disabled')
            self.StopBut.config(state='normal')
            self.OpenBut.config(state='disabled')
            self.FolderBut.config(state='disabled')
            if self.max_f_size_vl.get().isdigit():
                self.max_f_size = int(self.max_f_size_vl.get())
                self.max_f_size = (self.max_f_size * 1024 * 1024) - 128
            else:
                self.max_f_size = (10 * 1024 * 1024) - 128    # bin file max size
                self.max_f_size_vl.set('10')
            log.debug("rec_thread start")
            log.debug("bin file size = %d" % self.max_f_size)
        
    #------------------------------------------------------------------------------------------------------------------
    def StopBut_Click(self):
        self.StartBut.config(state='disabled')
        self.StopBut.config(state='disabled')
        self.OpenBut.config(state='normal')
        self.FolderBut.config(state='normal')
        self.SchNextBut.config(state='normal')
        self.SchPrevBut.config(state='normal')
        self.rec_start = 0
    
    def com_sel_chg(self, event=None):
        if event:
            self.com_sel = event.widget.get()
        else:
            log.debug("Not have event")
    
    #------------------------------------------------------------------------------------------------------------------
    def SchNextBut_Click(self):
        search_txt = self.SearchCont.get()
        search_pos = self.text.search(search_txt, index=str(self.pos), stopindex="end")
        if search_pos:
            self.text.see(search_pos)
            self.text.tag_delete('SchNext')
            pos_s = search_pos.split('.')
            pos_dec = int(pos_s[1]) + len(search_txt)
            search_end = "%s.%s" % (pos_s[0], str(pos_dec))
            # log.debug("%s %s" % (search_pos, search_end))
            self.text.tag_add("SchNext", search_pos, search_end)
            self.text.tag_config('SchNext', background='SkyBlue')
            
            pos_dec = int(pos_s[1]) + len(search_txt) + 1
            search_end = "%s.%s" % (pos_s[0], str(pos_dec))
            self.pos = float(search_end)
        else:
            self.pos = 0.0
            # log.debug("SchNextBut not find")
    
    def SchPrevBut_Click(self):
        search_txt = self.SearchCont.get()
        search_pos = self.text.search(search_txt, index=str(self.pos), stopindex="1.0", backwards=True)
        if search_pos:
            # log.debug(search_pos)
            self.text.see(search_pos)
            self.text.tag_delete('SchPrev')
            pos_s = search_pos.split('.')
            pos_dec = int(pos_s[1]) + len(search_txt)
            search_end = "%s.%s" % (pos_s[0], str(pos_dec))
            self.text.tag_add('SchPrev', search_pos, search_end)
            self.text.tag_config('SchPrev', background='yellow')
            self.pos = float(search_pos)
        else:
            self.pos = float(self.text.index(tk.END)) - 1.0
            # log.debug("SchPrevBut not find")
    
    #------------------------------------------------------------------------------------------------------------------
    def color_but_sel(self):
        self.color_chk = self.color_var.get()
        # log.debug("%d" % self.color_var.get())
    
    def all_but_sel(self):
        self.all_chk = self.all_var.get()
    
    def en_mp_but_sel(self):
        self.en_mp_chk = self.en_mp_var.get()
    
    def del_txt_but(self):
        self.del_txt_chk = self.del_txt_var.get()
        # log.debug("%d" % self.del_txt_var.get())
    
    def del_bin_but(self):
        self.del_bin_chk = self.del_bin_var.get()
        # log.debug("%d" % self.del_bin_var.get())
    
    def dis_show_but(self):
        self.dis_show_chk = self.dis_show_var.get()
    
    def en_systime_but(self): #[U0830][Wade] Add system timestamp
        self.en_systime_chk = self.en_systime_var.get()
    
    #------------------------------------------------------------------------------------------------------------------
    def FolderBut_Click(self):
        self.StartBut.config(state='disabled')
        self.OpenBut.config(state='disabled')
        self.FolderBut.config(state='disabled')
        self.SchNextBut.config(state='disabled')
        self.SchPrevBut.config(state='disabled')
        parsing_path =  filedialog.askdirectory(title = "Select folder")
        # log.debug(parsing_path)
        if len(parsing_path)==0:
            self.StartBut.config(state='normal')
            self.OpenBut.config(state='normal')
            self.FolderBut.config(state='normal')
            self.SchNextBut.config(state='normal')
            self.SchPrevBut.config(state='normal')
            # log.debug("Not have select file!!!")
            return
        
        self.parsing_fn = []
        existFile = glob.glob(parsing_path + '\\*.bin')
        #-- Found minimum file number
        min_value = 0xFFFFFFFF
        for ex_file in existFile:
            fn = ex_file.split('.')[0]
            fn_split = fn.split('_')
            fn_len = len(fn_split)
            if fn_split[fn_len-1]=='Stop':  fn_num = int(fn_split[fn_len-2])
            else:                           fn_num = int(fn_split[fn_len-1])
            if fn_num<min_value:    min_value=fn_num
        #--
        max_value = min_value + len(existFile)
        for lp in range(min_value, max_value):
            file_n3 = '{0:03d}.bin'.format(lp)
            file_n4 = '{0:04d}.bin'.format(lp)
            file_n5 = '{0:05d}.bin'.format(lp)
            find_f = 0
            for ex_file in existFile:
                # log.debug(ex_file)
                if ex_file.endswith(file_n3):
                    find_f = 1
                    # log.debug(ex_file)
                    break
                if ex_file.endswith(file_n4):
                    find_f = 1
                    # log.debug(ex_file)
                    break
                if ex_file.endswith(file_n5):
                    find_f = 1
                    # log.debug(ex_file)
                    break
                if ex_file.endswith("Stop.bin"):
                    find_f = 1
                    break
            
            if find_f:  self.parsing_fn.append(ex_file)
        
        if find_f==0:
            self.StartBut.config(state='normal')
            self.OpenBut.config(state='normal')
            self.FolderBut.config(state='normal')
            self.SchNextBut.config(state='normal')
            self.SchPrevBut.config(state='normal')
            return
        
        #------------------------------------------------------------------------------------------
        parsing_thread = threading.Thread(target=self.parsing_folder_thread, name='Parsing Folder')
        parsing_thread.setDaemon(True)
        parsing_thread.start()
        
    #------------------------------------------------------------------------------------------------------------------
    def parsing_folder_thread(self):
        #------------------------------------------------------------------------------------------
        #-- Check LogSetting.dat
        # log.debug("Check LogSetting.dat")
        try:
            with open(self.LogSettingPath) as source:
                log_f = source.read().splitlines()
                self.log_open = 1
                md5_obj = hashlib.md5()
                for line in log_f:
                    md5_obj.update(line.encode("utf-8"))
                chk_log_md5 = md5_obj.hexdigest()
                if chk_log_md5 != self.log_md5:
                    self.log_md5 = chk_log_md5
                    log.debug("LogSetting.dat has differenct")
                    del self.parsing
                    self.parsing = event_parsing(log_f)
                    for lp in range(0, len(self.parsing.color_st)):
                        try:
                            self.text.tag_config(self.parsing.color_st[lp], foreground = self.parsing.color_st[lp])
                        except:
                            self.parsing.color_st[lp] = "BLACK"
                            self.text.tag_config(self.parsing.color_st[lp], foreground = self.parsing.color_st[lp])
        except:
            log.debug("Check LogSetting.dat fail!!")
            self.rec_start = 0
            self.rec_th_fg = 1
            self.StartBut.config(state='normal')
            self.OpenBut.config(state='normal')
            self.FolderBut.config(state='normal')
            self.SchNextBut.config(state='disabled')
            self.SchPrevBut.config(state='disabled')
            return
        
        #------------------------------------------------------------------------------------------
        #-- Open store file
        # log.debug("Open store file")
        ticks = str(int(time.time()))
        if os.name == "nt": self.txt_fd = "\\Txt_" + ticks + '\\'
        else:               self.txt_fd = "/Txt_" + ticks + '/'
        store_path = self.store_fd + ticks
        if not os.path.exists("Store"):
            os.makedirs("Store")
        
        if not os.path.exists(store_path):
            os.makedirs(store_path)
            os.makedirs(store_path+self.txt_fd)
        
        store_num = 0
        # txt_path = store_path+self.txt_fd+ticks+"_{0:04d}".format(store_num) + ".txt"
        # txt_f = open(txt_path, mode='wt')
        
        #-----------------------------------------------------------------------
        #-- Parsing Variable
        debug = 1                   # debug parsing error.  If enable parsing file will write debug information
        
        # rec_remain = len(self.parsing_f)
        
        
        
        if self.all_chk:
            txt_path = store_path+self.txt_fd+ticks+"_all.txt"
            txt_all_f = open(txt_path, mode='wt')
        
        #-----------------------------------------------------------------------
        # self.text.config(state="normal")
        # self.text.delete(1.0, tk.END)
        #-----------------------------------------------------------------------
        for fn_lp in range(0, len(self.parsing_fn)):
            with open(self.parsing_fn[fn_lp], 'rb') as source:
                self.parsing_f = source.read()
                # log.debug("self.parsing_fn[fn_lp] = %s" % self.parsing_fn[fn_lp])
            
            txt_path = store_path+self.txt_fd+ticks+"_{0:04d}".format(store_num) + ".txt"
            txt_f = open(txt_path, mode='wt')
            store_num += 1
            rec_remain = len(self.parsing_f)
            rec_r_ptr = 0
            shw_remain = 0
            show_err = ''
            while rec_remain:
                if rec_remain < 2:
                    if(self.debug): txt_f.write("tag break rec_remain = %d \n" % (rec_remain))
                    break
                
                rec_r_end = rec_r_ptr + 2
                try:
                    log_idx = self.parsing.tag.index(self.parsing_f[rec_r_ptr:rec_r_end])
                except:
                    show_err = show_err + ("%02x " % self.parsing_f[rec_r_ptr])
                    rec_r_ptr += 1
                    rec_remain -= 1
                    continue
                
                if (self.parsing.content[log_idx][1]>2) or (len(self.parsing.tag_num[log_idx])>1):  # SATA only
                    find_tag = 0
                    for tag_lp in range(0, len(self.parsing.tag_num[log_idx])):
                        rec_r_end = rec_r_ptr +  self.parsing.tag_num[log_idx][tag_lp]
                        try:
                            log_idx = self.parsing.tag2.index(self.parsing_f[rec_r_ptr:rec_r_end], log_idx)
                            find_tag = 1
                            break
                        except:
                            continue
                    
                    if find_tag==0:
                        show_err = show_err + ("SATA %02x " % self.parsing_f[rec_r_ptr])
                        rec_r_ptr += 1
                        rec_remain -= 1
                        continue
                
                if len(show_err):
                    if self.color_chk==0:
                        show_err += "\n"
                        txt_f.write(show_err)
                        if self.all_chk:    txt_all_f.write(show_err)
                        show_err = ''
                    else:
                        show_err += "\n"
                        txt_f.write(show_err)
                        if self.all_chk:    txt_all_f.write(show_err)
                        show_err = ''
                
                if self.parsing.content[log_idx][5] > (rec_remain - self.parsing.content[log_idx][1]):
                    # self.parsing_f[0:rec_remain] = self.parsing_f[rec_r_ptr:rec_r_end]
                    # rec_w_ptr = rec_remain
                    log.debug('Wrong file is %s' % self.parsing_fn[fn_lp])
                    if(self.debug): txt_f.write("break rec_r_ptr = %d rec_remain = %d \n" % (rec_r_ptr, rec_remain))
                    break
                
                log_end = rec_r_end + self.parsing.content[log_idx][5]
                try:
                    show_tuple = self.parsing.content[log_idx][7].unpack(self.parsing_f[rec_r_end:log_end])
                except:
                    log.debug("rec_r_end = %d  log_end = %d" % (rec_r_end, log_end))
                    log.debug(self.parsing.content[log_idx][2])
                    log.debug(self.parsing.content[log_idx][5])
                    log.debug(self.parsing.content[log_idx][6])
                    self.rec_start = 0
                    self.StartBut.config(state='normal')
                    self.StopBut.config(state='disabled')
                    self.OpenBut.config(state='normal')
                    self.FolderBut.config(state='normal')
                    self.SchNextBut.config(state='normal')
                    self.SchPrevBut.config(state='normal')
                    break
                
                if self.parsing.content[log_idx][4]:
                    try:
                        show = (self.parsing.content[log_idx][2] % show_tuple) + "\n"
                    except:
                        log.debug("error string = %s" % self.parsing.content[log_idx][2])
                        log.debug(show_tuple)
                        self.rec_start = 0
                        self.StartBut.config(state='normal')
                        self.StopBut.config(state='disabled')
                        self.OpenBut.config(state='normal')
                        self.FolderBut.config(state='normal')
                        self.SchNextBut.config(state='normal')
                        self.SchPrevBut.config(state='normal')
                        break
                else:
                    show = self.parsing.content[log_idx][2] + "\n"
                
                #----------------------------------------------------------------------------------
                txt_f.write(show)
                if self.all_chk:    txt_all_f.write(show)
                w_buf_end = rec_r_ptr + self.parsing.content[log_idx][8]
                
                #----------------------------------------------------------------------------------
                if shw_remain > 1000:
                    shw_remain = 0
                    self.label.config(text=str(rec_remain))
                else:
                    shw_remain += 1
                #----------------------------------------------------------------------------------
                
                rec_r_ptr = w_buf_end
                rec_remain -= self.parsing.content[log_idx][8]
                if rec_remain < 0:
                    log.debug("error rec_remain = %d" % rec_remain)
                    log.debug("error string = %s" % self.parsing.content[log_idx][2])
            txt_f.close()
        
        txt_all_f.close()
        #-- Parsing End
        #------------------------------------------------------------------------------------------
        self.label.config(text=str(rec_remain))
        
        self.StartBut.config(state='normal')
        self.OpenBut.config(state='normal')
        self.FolderBut.config(state='normal')
        self.SchNextBut.config(state='normal')
        self.SchPrevBut.config(state='normal')
        self.text.config(state="disable")
        # txt_f.close()
    #------------------------------------------------------------------------------------------------------------------
    
    def OpenBut_Click(self):
        store_num = 0
        
        self.StartBut.config(state='disabled')
        self.OpenBut.config(state='disabled')
        self.FolderBut.config(state='disabled')
        self.SchNextBut.config(state='disabled')
        self.SchPrevBut.config(state='disabled')
        parsing_path =  filedialog.askopenfilename(title = "Select file",filetypes = (("bin files","*.bin"),("all files","*.*")))
        if len(parsing_path)==0:
            self.StartBut.config(state='normal')
            self.OpenBut.config(state='normal')
            self.FolderBut.config(state='normal')
            self.SchNextBut.config(state='normal')
            self.SchPrevBut.config(state='normal')
            # log.debug("Not have select file!!!")
            return
        # log.debug(filename)
        
        #------------------------------------------------------------------------------------------
        #-- Start Parsing bin file
        with open(parsing_path, 'rb') as source:
            self.parsing_f = source.read()
        
        #------------------------------------------------------------------------------------------
        if self.en_mp_chk:
            parsing_th = threading.Thread(target=self.parsing_th, name='Parsing')
            parsing_th.setDaemon(True)
            parsing_th.start()
        else:
            parsing_thread = threading.Thread(target=self.parsing_thread, name='Parsing')
            parsing_thread.setDaemon(True)
            parsing_thread.start()
        
    def parsing_thread(self):
        #------------------------------------------------------------------------------------------
        #-- Check LogSetting.dat
        # log.debug("Check LogSetting.dat")
        log.debug("parsing_thread Start")
        ticks_s = int(time.time())
        try:
            with open(self.LogSettingPath) as source:
                log_f = source.read().splitlines()
                self.log_open = 1
                md5_obj = hashlib.md5()
                for line in log_f:
                    md5_obj.update(line.encode("utf-8"))
                chk_log_md5 = md5_obj.hexdigest()
                if chk_log_md5 != self.log_md5:
                    self.log_md5 = chk_log_md5
                    log.debug("LogSetting.dat has differenct")
                    del self.parsing
                    self.parsing = event_parsing(log_f)
                    for lp in range(0, len(self.parsing.color_st)):
                        try:
                            self.text.tag_config(self.parsing.color_st[lp], foreground = self.parsing.color_st[lp])
                        except:
                            self.parsing.color_st[lp] = "BLACK"
                            self.text.tag_config(self.parsing.color_st[lp], foreground = self.parsing.color_st[lp])
        except:
            log.debug("Check LogSetting.dat fail!!")
            self.rec_start = 0
            self.rec_th_fg = 1
            self.StartBut.config(state='normal')
            self.OpenBut.config(state='normal')
            self.FolderBut.config(state='normal')
            self.SchNextBut.config(state='disabled')
            self.SchPrevBut.config(state='disabled')
            return
        
        #------------------------------------------------------------------------------------------
        #-- Open store file
        # log.debug("Open store file")
        ticks = str(int(time.time()))
        store_path = ".\\Store\\" + ticks
        if not os.path.exists("Store"):
            os.makedirs("Store")
        
        if not os.path.exists(store_path):
            os.makedirs(store_path)
            os.makedirs(store_path+"\\Txt")
        
        txt_path = store_path+"\\Txt\\"+ticks+"_0000.txt"
        # txt_f = open(txt_path, mode='w', buffering=1000)
        txt_f = open(txt_path, mode='wt')
        
        #-----------------------------------------------------------------------
        #-- Splited File ----------------------------------------------------------------------------------------------
        if self.max_f_size_vl.get().isdigit():
            max_f_size = int(self.max_f_size_vl.get())
            max_f_size = max_f_size * 1024 * 1024 * 8
        else:
            max_f_size = max_f_size * 1024 * 1024 * 8
            self.max_f_size_vl.set('1')
        file_cnt = 0
        bin_size = 0
        
        #-----------------------------------------------------------------------
        #-- Parsing Variable
        debug = 1                   # debug parsing error.  If enable parsing file will write debug information
        rec_r_ptr = 0
        rec_remain = len(self.parsing_f)
        shw_remain = 0
        show_err = ''
        sh_color = ''
        show_ctl = 1
        sh_en = ''                  # for show log enhance performance
        
        #-----------------------------------------------------------------------
        # self.text.config(state="normal")
        # self.text.delete(1.0, tk.END)
        #-----------------------------------------------------------------------
        while rec_remain:
            if rec_remain < 2:
                if(self.debug): txt_f.write("tag break rec_remain = %d \n" % (rec_remain))
                break
            
            rec_r_end = rec_r_ptr + 2
            try:
                log_idx = self.parsing.tag.index(self.parsing_f[rec_r_ptr:rec_r_end])
            except:
                show_err = show_err + ("%02x " % self.parsing_f[rec_r_ptr])
                rec_r_ptr += 1
                rec_remain -= 1
                continue
            
            if (self.parsing.content[log_idx][1]>2) or (len(self.parsing.tag_num[log_idx])>1):  # SATA only
                find_tag = 0
                for tag_lp in range(0, len(self.parsing.tag_num[log_idx])):
                    rec_r_end = rec_r_ptr +  self.parsing.tag_num[log_idx][tag_lp]
                    try:
                        log_idx = self.parsing.tag2.index(self.parsing_f[rec_r_ptr:rec_r_end], log_idx)
                        find_tag = 1
                        break
                    except:
                        continue
                
                if find_tag==0:
                    show_err = show_err + ("SATA %02x " % self.parsing_f[rec_r_ptr])
                    rec_r_ptr += 1
                    rec_remain -= 1
                    continue
            
            if len(show_err):
                if self.color_chk==0:
                    show_err += "\n"
                    txt_f.write(show_err)
                    # sh_en += show_err
                    show_err = ''
                else:
                    # if len(sh_en):
                    #     self.text.insert(tk.END, sh_en, sh_color)
                    #     self.text.see(tk.END)
                    #     sh_en = ''
                    show_err += "\n"
                    txt_f.write(show_err)
                    # self.text.insert(tk.END, show_err, "red")
                    # self.text.see(tk.END)
                    show_err = ''
            
            if self.parsing.content[log_idx][5] > (rec_remain - self.parsing.content[log_idx][1]):
                # self.parsing_f[0:rec_remain] = self.parsing_f[rec_r_ptr:rec_r_end]
                rec_w_ptr = rec_remain
                if(self.debug): txt_f.write("break rec_r_ptr = %d rec_remain = %d \n" % (rec_r_ptr, rec_remain))
                break
            
            log_end = rec_r_end + self.parsing.content[log_idx][5]
            try:
                show_tuple = self.parsing.content[log_idx][7].unpack(self.parsing_f[rec_r_end:log_end])
            except:
                log.debug("rec_r_end = %d  log_end = %d" % (rec_r_end, log_end))
                log.debug(self.parsing.content[log_idx][2])
                log.debug(self.parsing.content[log_idx][5])
                log.debug(self.parsing.content[log_idx][6])
                self.rec_start = 0
                self.StartBut.config(state='normal')
                self.StopBut.config(state='disabled')
                self.OpenBut.config(state='normal')
                self.FolderBut.config(state='normal')
                self.SchNextBut.config(state='normal')
                self.SchPrevBut.config(state='normal')
                break
            
            if self.parsing.content[log_idx][4]:
                try:
                    show = (self.parsing.content[log_idx][2] % show_tuple) + "\n"
                except:
                    log.debug("error string = %s" % self.parsing.content[log_idx][2])
                    log.debug(show_tuple)
                    self.rec_start = 0
                    self.StartBut.config(state='normal')
                    self.StopBut.config(state='disabled')
                    self.OpenBut.config(state='normal')
                    self.FolderBut.config(state='normal')
                    self.SchNextBut.config(state='normal')
                    self.SchPrevBut.config(state='normal')
                    break
            else:
                show = self.parsing.content[log_idx][2] + "\n"
            
            #----------------------------------------------------------------------------------
            txt_f.write(show)
            w_buf_end = rec_r_ptr + self.parsing.content[log_idx][8]
            
            #-------------------------------------------------------------------------------------
            bin_size += self.parsing.content[log_idx][8]
            if bin_size>max_f_size:
                bin_size -= max_f_size
                file_cnt += 1
                txt_path = store_path+self.txt_fd+ticks+"_{0:04d}".format(file_cnt) + ".txt"
                # txt_path = store_path+"\\Txt\\"+ticks+"_{0:04d}".format(file_cnt) + ".txt"
                txt_f.close()
                txt_f = open(txt_path, 'w')
            
            #-------------------------------------------------------------------------------------
            # if show_ctl==1:
            #     sh_en = show
            #     if self.color_chk:  sh_color = self.parsing.content[log_idx][3]
            #     else:               sh_color = 'black'
            #     show_ctl = 2
            # elif show_ctl==2:
            #     if self.color_chk==0:
            #         if len(sh_en) > 8388608:
            #             self.text.insert(tk.END, sh_en, sh_color)
            #             self.text.see(tk.END)
            #             # txt_f.flush()
            #             sh_en = show
            #         else:   sh_en += show
            #     elif sh_color != self.parsing.content[log_idx][3]:
            #         if rec_remain < 1048576:
	        #             self.text.insert(tk.END, sh_en, sh_color)
	        #             self.text.see(tk.END)
            #         sh_en = show
            #         sh_color = self.parsing.content[log_idx][3]
            #     else:
            #         sh_en += show

            #----------------------------------------------------------------------------------
            if shw_remain > 1000:
                shw_remain = 0
                self.label.config(text=str(rec_remain))
            else:
                shw_remain += 1
            #----------------------------------------------------------------------------------
            
            rec_r_ptr = w_buf_end
            rec_remain -= self.parsing.content[log_idx][8]
            if rec_remain < 0:
                log.debug("error rec_remain = %d" % rec_remain)
                log.debug("error string = %s" % self.parsing.content[log_idx][2])
        
        # if self.color_chk==0:
        #     self.text.insert(tk.END, sh_en, sh_color)
        #     self.text.see(tk.END)
        #     self.label.config(text=str(rec_remain))
        #-- Parsing End
        #------------------------------------------------------------------------------------------
        self.label.config(text=str(rec_remain))
        log.debug('gap = %d' % (int(time.time())-ticks_s))
        log.debug("parsing_thread Stop")
        
        self.StartBut.config(state='normal')
        self.OpenBut.config(state='normal')
        self.FolderBut.config(state='normal')
        self.SchNextBut.config(state='normal')
        self.SchPrevBut.config(state='normal')
        self.text.config(state="disable")
        txt_f.close()
        
    #------------------------------------------------------------------------------------------------------------------
    def parsing_th(self):
        #------------------------------------------------------------------------------------------
        #-- Check LogSetting.dat
        # log.debug("Check LogSetting.dat")
        ticks_s = time.time()
        try:
            with open(self.LogSettingPath) as source:
                log_f = source.read().splitlines()
                self.log_open = 1
                md5_obj = hashlib.md5()
                for line in log_f:
                    md5_obj.update(line.encode("utf-8"))
                chk_log_md5 = md5_obj.hexdigest()
                if chk_log_md5 != self.log_md5:
                    self.log_md5 = chk_log_md5
                    log.debug("LogSetting.dat has differenct")
                    del self.parsing
                    self.parsing = event_parsing(log_f)
                    for lp in range(0, len(self.parsing.color_st)):
                        try:
                            self.text.tag_config(self.parsing.color_st[lp], foreground = self.parsing.color_st[lp])
                        except:
                            self.parsing.color_st[lp] = "BLACK"
                            self.text.tag_config(self.parsing.color_st[lp], foreground = self.parsing.color_st[lp])
        except:
            log.debug("Check LogSetting.dat fail!!")
            self.rec_start = 0
            self.rec_th_fg = 1
            self.StartBut.config(state='normal')
            self.OpenBut.config(state='normal')
            self.FolderBut.config(state='normal')
            self.SchNextBut.config(state='disabled')
            self.SchPrevBut.config(state='disabled')
            return
        
        #------------------------------------------------------------------------------------------
        #-- Open store file
        # log.debug("Open store file")
        ticks = str(int(time.time()))
        store_path = ".\\Store\\" + ticks
        if not os.path.exists("Store"):
            os.makedirs("Store")
        
        if not os.path.exists(store_path):
            os.makedirs(store_path)
            os.makedirs(store_path+"\\Txt")
        
        txt_path = store_path+"\\Txt\\"+ticks+"_0000.txt"
        # txt_f = open(txt_path, mode='w', buffering=1000)
        txt_f = open(txt_path, mode='wt')
        
        #-----------------------------------------------------------------------
        #-- Parsing Variable
        debug = 1                   # debug parsing error.  If enable parsing file will write debug information
        rec_r_ptr = 0
        rec_remain = len(self.parsing_f)
        self.label.config(text=str(rec_remain))
        shw_remain = 0
        show_err = ''
        sh_color = ''
        show_ctl = 1
        sh_en = ''                  # for show log enhance performance
        
        # rec_buf_size = 0x800000     # 0x800000 = 8M
        
        #-- Splited File ----------------------------------------------------------------------------------------------
        if self.max_f_size_vl.get().isdigit():
            max_f_size = int(self.max_f_size_vl.get())
            max_f_size = max_f_size * 1024 * 1024 * 8
        else:
            max_f_size = max_f_size * 1024 * 1024 * 8
            self.max_f_size_vl.set('1')
        file_cnt = 0
        bin_size = 0
        
        #-- Multi Process ---------------------------------------------------------------------------------------------
        cmd_qu = mp.Queue()
        rep_qu = mp.Queue()
        # parsing_ph = mp.Process(target=self.parsing_mp, args=(cmd_qu, rep_qu, self.parsing.tag, self.parsing.tag2, 
        #     self.parsing.tag_num, self.parsing.content, self.en_systime_chk, 0x800000, ))
        # parsing_ph.daemon = True
        # parsing_ph.start()
        parsing_ph = parsing_mp(cmd_qu, rep_qu, log_f, self.en_systime_chk, 0x800000)
        parsing_ph.start()
        rep_qu.get()
        #--------------------------------------------------------------------------------------------------------------
        cmd_qu.put([rec_remain, self.parsing_f])
        cmd_qu.put([0, self.parsing_f[0]])
        self.label.config(text=str(rec_remain))
        log.debug("max_f_size = 0x%08X" % max_f_size)
        
        while rec_remain:
            while rep_qu.empty()==1:
                None
            while True:
                log_size, show, color, raw = rep_qu.get()
                if rec_remain==0 or show=='Stop':
                    self.label.config(text=str(rec_remain))
                    rec_remain = 0
                    break
                txt_f.write(show)
                rec_remain -= log_size
                bin_size += log_size
                if bin_size>max_f_size:
                    bin_size -= max_f_size
                    file_cnt += 1
                    txt_path = store_path+self.txt_fd+ticks+"_{0:04d}".format(file_cnt) + ".txt"
                    # txt_path = store_path+"\\Txt\\"+ticks+"_{0:04d}".format(file_cnt) + ".txt"
                    txt_f.close()
                    txt_f = open(txt_path, 'w')
                
                # self.label.config(text=str(rec_remain))
                #--------------------------------------------------------------------------------------
                if shw_remain > 1000:
                    shw_remain = 0
                    self.label.config(text=str(rec_remain))
                else:
                    shw_remain += 1
                #--------------------------------------------------------------------------------------
            
        self.label.config(text=str(rec_remain))
        # log.debug('gap = %d' % (int(time.time())-ticks_s))
        log.debug('gap = %d' % (time.time()-ticks_s))
        # log.debug("parsing_th Stop")
        # parsing_ph.process.join(8)
        
        parsing_ph.stop()
        # log.debug("parsing_th join end")
        
        self.StartBut.config(state='normal')
        self.OpenBut.config(state='normal')
        self.FolderBut.config(state='normal')
        self.SchNextBut.config(state='normal')
        self.SchPrevBut.config(state='normal')
        self.text.config(state="disable")
        txt_f.close()
    #------------------------------------------------------------------------------------------------------------------
    def display_stop(self):
        self.StartBut.config(state='normal')
        self.StopBut.config(state='disabled')
        self.OpenBut.config(state='normal')
        self.FolderBut.config(state='normal')
        self.SchNextBut.config(state='normal')
        self.SchPrevBut.config(state='normal')
    
    def zipCompress(self):
        fp = zipfile.ZipFile(self.bin_zip, mode='a', compression=zipfile.ZIP_LZMA)
        fp.setpassword(b'ssdrive01')
        fp.write(self.cmp_bin_path)
        fp.close()
    
    def com_bytes(self, org, new, loc):
        org_len = len(org)
        new_len = len(new)
        if org_len!=new_len:
            log.debug('org_len=%d new_len=%d loc=%d' % (org_len, new_len, loc))
    
    def display_thread(self):
        log_idx = 0
        show_num = 0
        rec_w_ptr = 0
        rec_r_ptr = 0
        rec_num = 0
        rec_remain = 0
        rec_limit = 65536 - 16      # CP210x buffer only 65536.  If > 65536 will lost data.
        # rec_buf = bytearray(0)
        rec_buf = bytes()
        show_err = ''
        store_num = 0
        del_num = 0
        ticks = 0
        bin_size = 0
        show_ctl = 0
        
        #------------------------------------------------------------------------------------------
        #-- Open COM port
        com = serial.Serial(self.com_sel, 921600, timeout=0)
        if com.isOpen():
            self.rec_th_fg = 1
        else:
            log.debug("%s can't open" % self.com_sel)
            self.rec_start = 0
            self.rec_th_fg = 1
            self.display_stop()
            com.close()
            return
        
        #------------------------------------------------------------------------------------------
        #-- Check LogSetting.dat
        try:
            with open(self.LogSettingPath) as source:
                log_f = source.read().splitlines()
                self.log_open = 1
                md5_obj = hashlib.md5()
                for line in log_f:
                    md5_obj.update(line.encode("utf-8"))
                chk_log_md5 = md5_obj.hexdigest()
                if chk_log_md5 != self.log_md5:
                    self.log_md5 = chk_log_md5
                    log.debug("LogSetting.dat has differenct")
                    del self.parsing
                    self.parsing = event_parsing(log_f)
                    for lp in range(0, len(self.parsing.color_st)):
                        try:
                            self.text.tag_config(self.parsing.color_st[lp], foreground = self.parsing.color_st[lp])
                        except:
                            self.parsing.color_st[lp] = "BLACK"
                            self.text.tag_config(self.parsing.color_st[lp], foreground = self.parsing.color_st[lp])
        except:
            log.debug("Check LogSetting.dat fail!!")
            self.rec_start = 0
            self.rec_th_fg = 1
            self.display_stop()
            com.close()
            return
        
        #------------------------------------------------------------------------------------------
        #-- Open store file
        ticks = str(int(time.time()))
        
        if os.name == "nt":
            self.bin_fd = "\\Bin_" + ticks + '\\'
            self.txt_fd = "\\Txt_" + ticks + '\\'
        else:
            self.bin_fd = "/Bin_" + ticks + '/'
            self.txt_fd = "/Txt_" + ticks + '/'
        
        store_path = self.store_fd + ticks
        if not os.path.exists("Store"):
            os.makedirs("Store")
        
        if not os.path.exists(store_path):
            os.makedirs(store_path)
            os.makedirs(store_path+self.bin_fd)
            os.makedirs(store_path+self.txt_fd)
        
        self.file_name.config(text=ticks)
        bin_path = store_path+self.bin_fd+ticks+"_{0:04d}".format(store_num) + ".bin"
        bin_f = open(bin_path, 'wb')
        
        self.bin_zip = store_path+self.bin_fd+ticks+".7z"
        
        txt_path = store_path+self.txt_fd+ticks+"_{0:04d}".format(store_num) + ".txt"
        txt_f = open(txt_path, 'w')
        store_num += 1
        
        #------------------------------------------------------------------------------------------
        self.text.config(state="normal")
        self.text.delete(1.0, tk.END)
        #------------------------------------------------------------------------------------------
        #-- Parsing receive data
        while self.rec_start:
            rec_r_ptr = 0
            if com.in_waiting:
                if rec_remain==0:
                    rec_buf = bytes()
                rec_remain = com.in_waiting
                w_end = rec_w_ptr + rec_remain
                if rec_remain > rec_limit:
                    show_err = "buffer overflow!! in_waiting = %d \n" % (rec_remain)
                    log.debug(show_err)
                    txt_f.write(show_err)
                    self.text.insert(tk.END, show_err, "RED")
                    self.text.see(tk.END)
                # rec_buf[rec_w_ptr:w_end] = com.read(rec_remain)
                rec_buf = rec_buf + com.read(rec_remain)
                rec_remain = w_end
                if (self.dis_show_chk==0):
                    show_disable = w_end>>self.show_limit
                    if show_ctl==0 and show_disable:
                        show_ctl = 1
                        self.text.delete(1.0, 2.0)
                        self.text.insert(tk.END, "......\n", 'RED')
                        self.text.see(tk.END)
                    elif show_disable==0:
                        show_ctl = 0
                
                if(self.debug): txt_f.write("rec_w_ptr = %d rec_remain = %d \n" % (rec_w_ptr, rec_remain))
                self.label.config(text=str(w_end))
                rec_w_ptr = 0
            else:
                self.label.config(text='0')
                txt_f.flush()
                bin_f.flush()
                if com.in_waiting==0:   time.sleep(0.2)
            
            while rec_remain and self.rec_start:
                if com.in_waiting > self.max_buf:
                    # rec_buf[0:rec_remain] = rec_buf[rec_r_ptr:w_end]
                    rec_buf = rec_buf[rec_r_ptr:w_end]
                    rec_w_ptr = rec_remain
                    if(self.debug):
                        txt_f.write("com.in_waiting break rec_r_ptr = %d rec_remain = %d \n" % (rec_r_ptr, rec_remain))
                        txt_f.write("%02x %02x %02x %02x " % (rec_buf[rec_r_ptr], rec_buf[rec_r_ptr+1], 
                            rec_buf[rec_r_ptr+2], rec_buf[rec_r_ptr+3]))
                    break
                elif rec_remain < 2:
                    # rec_buf[0:rec_remain] = rec_buf[rec_r_ptr:w_end]
                    rec_buf = rec_buf[rec_r_ptr:w_end]
                    rec_w_ptr = rec_remain
                    if(self.debug): txt_f.write("tag break rec_r_ptr = %d rec_remain = %d \n" % (rec_r_ptr, rec_remain))
                    break
                
                rec_r_end = rec_r_ptr + 2
                try:
                    log_idx = self.parsing.tag.index(rec_buf[rec_r_ptr:rec_r_end])
                except:
                    bin_size += 1
                    bin_f.write(rec_buf[rec_r_ptr:(rec_r_ptr+1)])
                    show_err = show_err + ("%02x " % rec_buf[rec_r_ptr])
                    rec_r_ptr += 1
                    rec_remain -= 1
                    if rec_remain==0:
                        rec_buf = bytes()
                    continue
                
                if (self.parsing.content[log_idx][1]>2) or (len(self.parsing.tag_num[log_idx])>1):  # SATA only
                    find_tag = 0
                    for tag_lp in range(0, len(self.parsing.tag_num[log_idx])):
                        rec_r_end = rec_r_ptr +  self.parsing.tag_num[log_idx][tag_lp]
                        try:
                            log_idx = self.parsing.tag2.index(rec_buf[rec_r_ptr:rec_r_end], log_idx)
                            find_tag = 1
                            break
                        except:
                            continue
                    
                    if find_tag==0:
                        bin_size += 1
                        bin_f.write(rec_buf[rec_r_ptr:(rec_r_ptr+1)])
                        show_err = show_err + ("SATA %02x " % rec_buf[rec_r_ptr])
                        rec_r_ptr += 1
                        rec_remain -= 1
                        continue
                
                if len(show_err):
                    show_err = show_err + ("error byte = 0x%x" % bin_size)
                    show_err += "\n"
                    txt_f.write(show_err)
                    # log.debug("show_err")
                    if show_ctl==0 and (self.dis_show_chk==0):
                        self.text.delete(1.0, 2.0)
                        self.text.insert(tk.END, show_err, "red")
                        self.text.see(tk.END)
                    show_err = ''
                
                if self.parsing.content[log_idx][5] > (rec_remain - self.parsing.content[log_idx][1]):
                    # rec_buf[0:rec_remain] = rec_buf[rec_r_ptr:w_end]
                    rec_buf = rec_buf[rec_r_ptr:w_end]
                    rec_w_ptr = rec_remain
                    if(self.debug): txt_f.write("break rec_r_ptr = %d rec_remain = %d \n" % (rec_r_ptr, rec_remain))
                    break
                
                log_end = rec_r_end + self.parsing.content[log_idx][5]
                try:
                    show_tuple = self.parsing.content[log_idx][7].unpack(rec_buf[rec_r_end:log_end])
                except:
                    log.debug("rec_r_end = %d  log_end = %d" % (rec_r_end, log_end))
                    log.debug(self.parsing.content[log_idx][2])
                    log.debug(self.parsing.content[log_idx][5])
                    log.debug(self.parsing.content[log_idx][6])
                    self.rec_start = 0
                    break
                    
                #[U0830][Wade] Add system timestamp
                if self.en_systime_chk:
                    sysTimestamp = time.localtime()
                    current_time = time.strftime("***%Y/%m/%d_%H-%M-%S***", sysTimestamp)
                else:
                    current_time = ""
                
                if self.parsing.content[log_idx][4]:
                    try:
                        show = current_time+(self.parsing.content[log_idx][2] % show_tuple) + "\n"
                    except:
                        log.debug("error string = %s" % self.parsing.content[log_idx][2])
                        log.debug(show_tuple)
                        self.rec_start = 0
                        break
                else:
                    show = current_time+self.parsing.content[log_idx][2] + "\n"
                
                #----------------------------------------------------------------------------------
                txt_f.write(show)
                bin_size += self.parsing.content[log_idx][8]
                w_buf_end = rec_r_ptr + self.parsing.content[log_idx][8]
                bin_f.write(rec_buf[rec_r_ptr:w_buf_end])
                if bin_size > self.max_f_size:
                    txt_f.close()
                    bin_f.close()
                    
                    if self.del_txt_chk:
                        self.cmp_bin_path = bin_path
                        zipCompress_th = threading.Thread(target=self.zipCompress, name='zipCompress')
                        zipCompress_th.setDaemon(True)
                        zipCompress_th.start()
                    
                    bin_size = 0
                    bin_path = store_path+self.bin_fd+ticks+"_{0:04d}".format(store_num) + ".bin"
                    bin_f = open(bin_path, 'wb')
                    txt_path = store_path+self.txt_fd+ticks+"_{0:04d}".format(store_num) + ".txt"
                    txt_f = open(txt_path, 'w')
                    store_num += 1
                    if self.del_txt_chk and ((store_num-del_num) > int(self.max_f_num_vl.get())):
                        txt_path = store_path+self.txt_fd+ticks+"_{0:04d}".format(del_num) + ".txt"
                        os.remove(txt_path)
                        del_num += 1
                    
                    if self.del_bin_chk and ((store_num-del_num) > int(self.max_f_num_vl.get())):
                        bin_path = store_path+self.bin_fd+ticks+"_{0:04d}".format(del_num) + ".bin"
                        os.remove(bin_path)
                        del_num += 1
                
                #----------------------------------------------------------------------------------
                # log.debug("show_ctl = %d" % show_ctl)
                if (show_ctl==0) and (self.dis_show_chk==0):
                    show_num += 1
                    if show_num > 8192:
                        self.text.delete(1.0, 1024.0)
                        show_num -= 1024
                    # if show_num > 8192: self.text.delete(1.0, 2.0)
                    # else:               show_num += 1
                    if self.color_chk==0:
                        self.text.insert(tk.END, show, 'black')
                    else:
                        self.text.insert(tk.END, show, self.parsing.content[log_idx][3])
                    self.text.see(tk.END)
                #----------------------------------------------------------------------------------
                
                rec_r_ptr = w_buf_end
                rec_remain -= self.parsing.content[log_idx][8]
                if rec_remain < 0:
                    log.debug("error rec_remain = %d" % rec_remain)
                    log.debug("error string = %s" % self.parsing.content[log_idx][2])
        
        #------------------------------------------------------------------------------------------
        if rec_remain or com.in_waiting:
            bin_f.write(rec_buf[rec_r_ptr:w_end])
            bin_f.write(com.read(com.in_waiting))
        
        txt_f.close()
        bin_f.close
        self.cmp_bin_path = bin_path
        self.zipCompress()
        com.close()
        self.display_stop()
        self.text.config(state="disable")
        log.debug("rec_thread stop")
        
#----------------------------------------------------------------------------------------------------------------------
    def display_th(self):
        show_num = 0
        rec_remain = 0
        store_num = 0
        del_num = 0
        ticks = 0
        bin_size = 0
        show_ctl = 0
        
        #------------------------------------------------------------------------------------------
        #-- Open COM port
        com = serial.Serial(self.com_sel, 921600, timeout=0)
        if com.isOpen():
            self.rec_th_fg = 1
        else:
            log.debug("%s can't open" % self.com_sel)
            self.rec_start = 0
            self.rec_th_fg = 1
            self.display_stop()
            com.close()
            return
        
        #------------------------------------------------------------------------------------------
        #-- Check LogSetting.dat
        log_f = None
        try:
            with open(self.LogSettingPath) as source:
                log_f = source.read().splitlines()
        except:
            log.debug("Check LogSetting.dat fail!!")
            self.rec_start = 0
            self.rec_th_fg = 1
            self.display_stop()
            com.close()
            return
        
        #------------------------------------------------------------------------------------------
        #-- Open store file
        ticks = str(int(time.time()))
        
        if os.name == "nt":
            self.bin_fd = "\\Bin_" + ticks + '\\'
            self.txt_fd = "\\Txt_" + ticks + '\\'
        else:
            self.bin_fd = "/Bin_" + ticks + '/'
            self.txt_fd = "/Txt_" + ticks + '/'
        
        store_path = self.store_fd + ticks
        if not os.path.exists("Store"):
            os.makedirs("Store")
        
        if not os.path.exists(store_path):
            os.makedirs(store_path)
            os.makedirs(store_path+self.bin_fd)
            os.makedirs(store_path+self.txt_fd)
        
        self.file_name.config(text=ticks)
        bin_path = store_path+self.bin_fd+ticks+"_{0:04d}".format(store_num) + ".bin"
        bin_f = open(bin_path, 'wb')
        
        self.bin_zip = store_path+self.bin_fd+ticks+".7z"
        
        txt_path = store_path+self.txt_fd+ticks+"_{0:04d}".format(store_num) + ".txt"
        txt_f = open(txt_path, 'w')
        store_num += 1
        
        #------------------------------------------------------------------------------------------
        self.text.config(state="normal")
        self.text.delete(1.0, tk.END)
        #-- Multi Process ---------------------------------------------------------------------------------------------
        cmd_qu = mp.Queue()
        rep_qu = mp.Queue()
        parsing_ph = parsing_mp(cmd_qu, rep_qu, log_f, self.en_systime_chk, 0x800000)
        parsing_ph.start()
        rep_qu.get()
        #--------------------------------------------------------------------------------------------------------------
        #-- Parsing receive data
        while self.rec_start:
            if com.in_waiting:
                rec_size = com.in_waiting
                rec_data = com.read(rec_size)
                cmd_qu.put([rec_size, rec_data])
                rec_remain += rec_size
            else:   time.sleep(0.2)
            
            self.label.config(text=str(rec_remain))
            while rep_qu.empty()==0:
                log_size, show, color, raw = rep_qu.get()
                txt_f.write(show)
                bin_size += log_size
                rec_remain -= log_size
                
                bin_f.write(raw)
                if bin_size > self.max_f_size:
                    txt_f.close()
                    bin_f.close()
                    
                    self.cmp_bin_path = bin_path
                    zipCompress_th = threading.Thread(target=self.zipCompress, name='zipCompress')
                    zipCompress_th.setDaemon(True)
                    zipCompress_th.start()
                    
                    bin_size = 0
                    bin_path = store_path+self.bin_fd+ticks+"_{0:04d}".format(store_num) + ".bin"
                    bin_f = open(bin_path, 'wb')
                    txt_path = store_path+self.txt_fd+ticks+"_{0:04d}".format(store_num) + ".txt"
                    txt_f = open(txt_path, 'w')
                    store_num += 1
                    if self.del_txt_chk and ((store_num-del_num) > int(self.max_f_num_vl.get())):
                        txt_path = store_path+self.txt_fd+ticks+"_{0:04d}".format(del_num) + ".txt"
                        os.remove(txt_path)
                        del_num += 1
                    
                    if self.del_bin_chk and ((store_num-del_num) > int(self.max_f_num_vl.get())):
                        bin_path = store_path+self.bin_fd+ticks+"_{0:04d}".format(del_num) + ".bin"
                        os.remove(bin_path)
                        del_num += 1
                
                if rep_qu.qsize() > 8192:
                    if show_ctl==0:
                        self.text.delete(1.0, 2.0)
                        self.text.insert(tk.END, "......\n", 'RED')
                        self.text.see(tk.END)
                    show_ctl = 1
                else:   show_ctl = 0
                
                if (show_ctl==0) and (self.dis_show_chk==0):
                    show_num += 1
                    if show_num > 8192:
                        self.text.delete(1.0, 1024.0)
                        show_num -= 1024
                    self.text.insert(tk.END, show, color)
                    self.text.see(tk.END)
        #--------------------------------------------------------------------------------------------------------------
        cmd_qu.put([0, 0])
        parsing_ph.stop()
        
        txt_f.close()
        bin_f.close
        self.cmp_bin_path = bin_path
        self.zipCompress()
        com.close()
        self.display_stop()
        self.text.config(state="disable")
        log.debug("rec_thread stop")
#----------------------------------------------------------------------------------------------------------------------
    def parsing_mp(self, cmd_qu, rep_qu, tag, tag2, tag_num, content, en_systime_chk, rec_buf_size):
        rec_w_ptr = 0
        rec_r_ptr = 0
        rec_remain = 0
        rec_buf = bytearray(rec_buf_size)
        err_cnt = 0
        err_buf_size = 0x10000      # 0x10000 = 64K
        err_buf = bytearray(err_buf_size)
        rec_start = 1
        log_size = 0
        log_end = 0
        
        rep_qu.put(0)
        while rec_start:
            size, data = cmd_qu.get()
            rec_remain = rec_w_ptr + size
            if size==0:
                rep_qu.put([rec_remain, "Stop", 'red', rec_buf[0:rec_remain]])
                break
            
            if rec_remain>rec_buf_size:
                log.debug("Receive too much data.")
                break
            rec_buf[rec_w_ptr:rec_remain] = data
            rec_w_ptr = rec_remain
            rec_r_ptr = 0
            
            while rec_remain:
                if rec_remain < 2:
                    rec_buf[0:rec_remain] = rec_buf[rec_r_ptr:rec_w_ptr]
                    rec_w_ptr = rec_remain
                    break
                
                rec_r_end = rec_r_ptr + 2
                try:
                    log_idx = tag.index(rec_buf[rec_r_ptr:rec_r_end])
                except:
                    err_buf[err_cnt] = rec_buf[rec_r_ptr]
                    err_cnt += 1
                    rec_r_ptr += 1
                    rec_remain -= 1
                    continue
                
                #-- SATA only -----------------------------------------------------------------------------------------
                if (content[log_idx][1]>2) or (len(tag_num[log_idx])>1):  
                    find_tag = 0
                    for tag_lp in range(0, len(tag_num[log_idx])):
                        rec_r_end = rec_r_ptr +  tag_num[log_idx][tag_lp]
                        try:
                            log_idx = tag2.index(rec_buf[rec_r_ptr:rec_r_end], log_idx)
                            find_tag = 1
                            break
                        except:
                            continue
                    
                    if find_tag==0:
                        err_buf[err_cnt] = rec_buf[rec_r_ptr]
                        err_cnt += 1
                        rec_r_ptr += 1
                        rec_remain -= 1
                        continue
                
                #------------------------------------------------------------------------------------------------------
                if err_cnt:
                    show_err = ''
                    if err_cnt>err_buf_size:
                        log.debug("Too Much Error Data")
                        rec_start = 0
                        break
                    for lp in range(0, err_cnt):
                        show_err = show_err + ("%02x " % err_buf[lp])
                    show_err = show_err + '\n'
                    rep_qu.put([err_cnt, show_err, 'red', err_buf[0:err_cnt]])
                    err_cnt = 0
                
                log_size = content[log_idx][8]
                if log_size > rec_remain:
                    rec_buf[0:rec_remain] = rec_buf[rec_r_ptr:rec_w_ptr]
                    rec_w_ptr = rec_remain
                    break
                
                log_end = rec_r_end + content[log_idx][5]
                try:
                    show_tuple = content[log_idx][7].unpack(rec_buf[rec_r_end:log_end])
                except:
                    log.debug("rec_r_end = %d  log_end = %d" % (rec_r_end, log_end))
                    log.debug(content[log_idx][2])
                    log.debug(content[log_idx][5])
                    log.debug(content[log_idx][6])
                    log.debug("Please Check LogSetting.dat file")
                    rec_start = 0
                    break
                
                #[U0830][Wade] Add system timestamp
                if content[log_idx][4]:
                    try:
                        show = (content[log_idx][2] % show_tuple) + "\n"
                    except:
                        log.debug("error string = %s" % content[log_idx][2])
                        log.debug(show_tuple)
                        rec_start = 0
                        break
                else:
                    show = content[log_idx][2] + "\n"
                
                if en_systime_chk:
                    sysTimestamp = time.localtime()
                    current_time = time.strftime("***%Y/%m/%d_%H-%M-%S***", sysTimestamp)
                    show = current_time + show
                
                rep_qu.put([log_size, show, content[log_idx][3], rec_buf[rec_r_ptr:log_end]])
                rec_r_ptr = log_end
                rec_remain -= log_size
                
        
    #------------------------------------------------------------------------------------------------------------------
    def get_device_ip_address(self):
        result = []
        try:
            if os.name == "nt":
                # On Windows
                result.append("Running on Windows")
                hostname = socket.gethostname()
                result.append(hostname)
                
                anydesk_path = "C:\\ProgramData\\AnyDesk\\system.conf"
                if os.path.exists(anydesk_path):
                    with open(anydesk_path) as source:
                        anydesk_f = source.read().splitlines()
                        for lp in range(0, len(anydesk_f)):
                            split_str = anydesk_f[lp].split('=')
                            if (len(split_str)>=2) and (split_str[0]=='ad.anynet.alias'):
                                result.append(split_str[1])
                
                host = socket.gethostbyname(hostname)
                gethost = socket.gethostbyname_ex(hostname)
                for lp in range(0, len(gethost[2])):
                    result.append(gethost[2][lp])
                    # result.append(get_mac_address(ip=gethost[2][lp]))
                return result

            elif os.name == "posix":
                
                # result.append("Linux")
                
                anydesk_path = "/etc/anydesk/system.conf"
                if os.path.exists(anydesk_path):
                    with open(anydesk_path) as source:
                        anydesk_f = source.read().splitlines()
                        for lp in range(0, len(anydesk_f)):
                            split_str = anydesk_f[lp].split('=')
                            if (len(split_str)>=2) and (split_str[0]=='ad.anynet.alias'):
                                result.append(split_str[1])
                
                cmd = "ifconfig wlan0"
                rsp=subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
                rsp_str = rsp.communicate()[0].decode('ascii').splitlines()
                
                if rsp_str[1].split()[0]=='inet':
                    result.append(rsp_str[1].split()[1])
                    return result
                else:
                    result.append("wlan0 Can't get IP")
                
                cmd = "ifconfig eth0"
                rsp=subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
                rsp_str = rsp.communicate()[0].decode('ascii').splitlines()
                
                if rsp_str[1].split()[0]=='inet':
                    result.append(rsp_str[1].split()[1])
                else:
                    result.append("eth0 Can't get IP")

                return result
            
            else:
                result = os.name + " not supported yet."
                return result
        except:
            return ["Could not detect ip address"]
    
    def ice_thread(self):
        message = self.get_device_ip_address()
        # message = ['Test', 'Try']
        log.debug(message)
        
        # hostname = socket.gethostname()
        # log.debug("%s" % hostname)
        # local_ip = socket.gethostbyname(hostname)
        # log.debug("%s" % local_ip)
        # gd_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # while self.ice_serve:
        #     self.
    
    #------------------------------------------------------------------------------------------------------------------

#----------------------------------------------------------------------------------------------------------------------
#-- class event_parsing
class event_parsing:
    def __init__(self, log_f):
    #------------------------------------------------------------------------------------------------------------------
    # Global variable
    #------------------------------------------------------------------------------------------------------------------
        self.log_f = log_f      # LogSetting.dat file
        self.tag = []           # Log's judge tag.  Only 2 byte.  bytes type.
        self.tag2 = []          # Same as full tag for search.  bytes type.
        self.tag_num = []       # 2 dimensional.  Ex: [0][0]:First tag size.  [0][1]:Second tag size
        self.content = []       # All parsing content 2 dimensional.  Ex: [0][0]:Full Tag, bytes type.
                                # [0][1]:Tag total size, [0][2]:Print string, [0][3]:Print color, 
                                # [0][4]:Total variable number, [0][5]:Total size - tag size, 
                                # [0][6]:log format for unpack, 
                                # [0][7]:struct object
                                # [0][8]:Total size
        self.color = 'red'      # For string color
        self.color_st = []      # Store all color
        
    #----------------------------------------------------------------------------------------------
        cont_ptr = 0
        val_fmt = []
        val_fmt.append(struct.Struct('H'))
        val_array_fmt = []
        val_array_fmt.append(struct.Struct('BB'))
        val_array_fmt.append(struct.Struct('BBB'))
        val_array_fmt.append(struct.Struct('BBBB'))
        for line in self.log_f:
            splitted = line.split('"')
            spl_cnt = len(splitted)
            # log.debug(line)
            if spl_cnt==1:
                str_tmp = list(shlex.shlex(splitted[0]))
                if (len(str_tmp) > 2) and (str_tmp[1] == 'SetMsgColor'):
                    self.color = str_tmp[3].lower()
                    if self.color not in self.color_st:
                        self.color_st.append(self.color)
                    # log.debug(self.color)
            elif (spl_cnt>=2) and (line[0]!=';'):
                str_tmp = list(shlex.shlex(splitted[0]))
                tag_tmp = 0
                tag_num = len(str_tmp)-1
                tag_array = bytearray(0)
                # self.tag.append((int(str_tmp[0], 16)<<8) | int(str_tmp[1], 16))
                self.tag.append(val_fmt[0].pack((int(str_tmp[1], 16)<<8) | int(str_tmp[0], 16)))
                for str_lp in range(0, tag_num):
                    # tag_tmp = (tag_tmp<<8) | int(str_tmp[str_lp], 16)
                    tag_tmp = tag_tmp | int(str_tmp[str_lp], 16) << (str_lp*8)
                    tag_array.append(int(str_tmp[str_lp], 16))
                # log.debug("tab_tmp = 0x%x" % tag_tmp)
                # log.debug(tag_array)
                # self.tag2.append(val_array_fmt[tag_num-2].pack(tag_array))
                self.tag2.append(tag_array)
                self.content.append([])
                self.content[cont_ptr].append(tag_tmp)                      # [0][0]
                self.content[cont_ptr].append(tag_num)                      # [0][1]
                # log.debug(splitted[1])
                self.content[cont_ptr].append(splitted[1])                  # [0][2]
                self.content[cont_ptr][2] = self.content[cont_ptr][2].replace('%0Ad', '%010d')
                self.content[cont_ptr][2] = self.content[cont_ptr][2].replace('%02D', '%02d')
                self.content[cont_ptr][2] = self.content[cont_ptr][2].replace('%04D', '%04d')
                self.content[cont_ptr][2] = self.content[cont_ptr][2].replace('%08D', '%08d')
                self.content[cont_ptr].append(self.color)                   # [0][3]
                
                size_tmp = []
                if spl_cnt==3:
                    str_tmp = list(shlex.shlex(splitted[2]))
                    for str_lp in range(0, len(str_tmp)):
                        if str_tmp[str_lp].isdigit() and int(str_tmp[str_lp]):
                            size_tmp.append(int(str_tmp[str_lp]))
                
                var_size = 0
                for size_lp in range(0, len(size_tmp)):
                    var_size += size_tmp[size_lp]
                total_var = var_size + tag_num
                total_var += (total_var%2)
                # log.debug(total_var)
                if var_size==0: self.content[cont_ptr].append(0)            # [0][4]
                else:           self.content[cont_ptr].append(len(size_tmp))# [0][4]
                self.content[cont_ptr].append(var_size)                     # [0][5]
                
                log_format = '>'
                self.content[cont_ptr].append('>')                          # [0][6]
                for size_lp in range(0, len(size_tmp)):
                    # self.content[cont_ptr].append(size_tmp[size_lp])
                    if size_tmp[size_lp]==1:    log_format += 'B'
                    elif size_tmp[size_lp]==2:  log_format += 'H'
                    elif size_tmp[size_lp]==4:  log_format += 'I'
                self.content[cont_ptr][6] = log_format
                self.content[cont_ptr].append(struct.Struct(log_format))    # [0][7]
                self.content[cont_ptr].append(total_var)                    # [0][8]
                
                cont_ptr += 1
        
    #----------------------------------------------------------------------------------------------
    #-- Calculate all tag size for SATA
        for lp in range(0, len(self.tag)):
            self.tag_num.append([])
            tag_find = self.tag[lp]
            self.tag_num[lp].append(self.content[lp][1])
            for lp2 in range(0, len(self.tag)):
                if lp2==lp: continue
                if tag_find==self.tag[lp2]:
                    try:
                        self.tag_num[lp].index(self.content[lp2][1])
                    except:
                        self.tag_num[lp].append(self.content[lp2][1])
            
        for lp in range(0, len(self.tag)):
            if len(self.tag_num[lp]) > 1:
                for lp2 in range(0, len(self.tag_num[lp])-1):
                    if self.tag_num[lp][lp2] < self.tag_num[lp][lp2+1]:
                        temp = self.tag_num[lp][lp2]
                        self.tag_num[lp][lp2] = self.tag_num[lp][lp2+1]
                        self.tag_num[lp][lp2+1] = temp
        
        # for lp in range(0, len(self.tag)):
        #     log.debug("self.tag_num[%d] len = %d" % (lp, len(self.tag_num[lp])))
        #     if len(self.tag_num[lp]) > 1:
        #         for lp2 in range(0, len(self.tag_num[lp])):
        #             log.debug("self.tag_num[%d][%d] = %d" % (lp, lp2, self.tag_num[lp][lp2]))
    #----------------------------------------------------------------------------------------------
    #-- Check all string validity
        show_tuple = (2013332098, 6670, 1122, 3344, 5566, 7788, 9900, 1234, 5678, 7654, 3210, 1234, 5678, 7654, 3210,
            6670, 1122, 3344, 5566, 7788, 9900, 1234, 5678, 7654, 3210, 1234, 5678, 7654, 3210)
        for lp in range(0, len(self.tag)):
            try:
                show = self.content[lp][2] % show_tuple[0:self.content[lp][4]]
            except:
                # log.debug("Total variable number = %d" % self.content[lp][4])
                # log.debug("Total size - tag size = %d" % self.content[lp][5])
                log.debug("wrong string = %02X %02X %s" % (self.content[lp][0]&0xFF, (self.content[lp][0]>>8)&0xFF, 
                    self.content[lp][2]))
        
    #------------------------------------------------------------------------------------------------------------------
    def tag_index(self, tag):
        try:
            ret_val = self.tag.index(tag)
            return ret_val
        except:
            return -1
    #------------------------------------------------------------------------------------------------------------------

#----------------------------------------------------------------------------------------------------------------------
#-- class uart
class uart:
    def __init__(self):
        self.cp210x_cnt = 0
        self.cp210x = []
        self.com_sel = ''
        
        for com, name, dev in serial.tools.list_ports.comports():
            # log.debug(com)
            # log.debug(name)
            # log.debug(dev)
            if 'CP210' in name:
                self.cp210x.append((com, name, dev))
                self.cp210x_cnt += 1

#----------------------------------------------------------------------------------------------------------------------
def main():
    ModSel = 0
    if len(sys.argv)==2:
        ModSel = int(sys.argv[1], 0)
    window = tk.Tk()
    app = py_window(master=window, ModSel=ModSel)
    if app.rec.cp210x_cnt:
        app.comboxlist.current(0)
    window.mainloop()

if __name__ == '__main__':
    log.info("%s Ver:%s" % (os.path.basename(__file__).split('.')[0], SW_Ver))
    main()
