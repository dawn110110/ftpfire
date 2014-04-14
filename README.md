ftpfire
=======

fire in the hole to the ftp | 只做交流学习瞎折腾之用.

- 需要 tornado

玩：

- 运行ftpserver:`python pyftp.py` (5000端口)
- 运行client尝试登陆. `cat dict.txt | python client.py`（目前用户名硬编码为ssdut，需要可以改）
- 并发的连接数：系统允许单个进程打开的最大文件数的1/2.
