# socket_sendfile
i use socket to solve my problems that when i want to send file from my pc to VMs, it's hard to find a way to get file or directory <br>
so i use socket programming to create a way to communicate between my pc with VMs <br> 
with this code you can choose VMs as server and in your pc there are 2 ways of manage file: <br> 

1. send file:<br>
   first you have to run server file like normal then run your pc code with command : <strong>sendFile.py "YOUR_FILE_NAME" "send"<strong><br>
   you can send file with type of .py .c or anything like that or file directory and be careful that it works with just file in the same         level with main code, i will add some feature that we can add file from other directory <br>

2. get file: <br>
   the same way with send file, you have to run server code and on your pc run : <strong> sendFile.py "YOUR_FILE_NAME_YOU_WANT_TO_GET" "get"<strong><br>

