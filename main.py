import socket             

# next create a socket object 
s = socket.socket()         
print ("Socket successfully created")

port = 12345                

s.bind(('', port))         
print ("socket binded to %s" %(port)) 

s.listen(5)     
print ("socket is listening")            

while True: 
    #establish a connection with client 
    c, addr = s.accept()     
    print ('Got connection from', addr )
    t = """from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True"""
    print(c.recv(1024).decode())
    c.send(t.encode())
    c.close() 
    #break
