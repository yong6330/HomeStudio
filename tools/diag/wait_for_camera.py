import socket
import time

def main():
    ip = "192.168.0.32"
    print("Waiting for camera (192.168.0.32) to reboot and come online...")
    
    # Wait for down
    start = time.time()
    for _ in range(15):
        s = socket.socket()
        s.settimeout(1.5)
        res = s.connect_ex((ip, 80))
        s.close()
        if res != 0:
            print(f"[{time.time()-start:.1f}s] Camera is now DOWN/REBOOTING (port 80 closed).")
            break
        time.sleep(2)

    # Wait for up
    for _ in range(30):
        s = socket.socket()
        s.settimeout(2.0)
        res = s.connect_ex((ip, 80))
        s.close()
        if res == 0:
            print(f"[{time.time()-start:.1f}s] Camera port 80 is UP!")
            # Also check RTSP port 554
            s2 = socket.socket()
            s2.settimeout(2.0)
            res2 = s2.connect_ex((ip, 554))
            s2.close()
            print(f"[{time.time()-start:.1f}s] Camera port 554 status: {res2}")
            if res2 == 0:
                print("Camera HTTP and RTSP are fully ONLINE!")
                return
        time.sleep(3)

if __name__ == "__main__":
    main()
