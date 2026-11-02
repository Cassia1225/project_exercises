import socket

host = "2001:2f8:200:35:ff22:d899:dce6:1039"

with socket.create_connection((host, 1884), timeout=3):
    print("IPv6で1884番に接続できました")