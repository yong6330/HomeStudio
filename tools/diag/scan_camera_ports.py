import concurrent.futures
import socket

def check_port(port):
    s = socket.socket()
    s.settimeout(0.5)
    res = s.connect_ex(("192.168.0.31", port))
    s.close()
    return port, res == 0

def main():
    print("Scanning ports on 192.168.0.31 (1..10000)...")
    open_ports = []
    # Test common camera ports first
    common_ports = [80, 554, 8000, 8080, 8443, 8554, 37777, 34567, 5000, 6000, 7000, 9000, 10000, 443, 8888, 8889]
    for p in common_ports:
        _, is_open = check_port(p)
        if is_open:
            open_ports.append(p)
    print("Common ports open:", open_ports)

    # Fast scan of 1..2000
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as ex:
        for p, is_open in ex.map(check_port, range(1, 2000)):
            if is_open and p not in open_ports:
                open_ports.append(p)
    print("All open ports found in 1..2000:", sorted(open_ports))

if __name__ == "__main__":
    main()
