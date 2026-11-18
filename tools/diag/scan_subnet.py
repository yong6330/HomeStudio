import concurrent.futures
import subprocess

def ping(i):
    ip = f"192.168.0.{i}"
    res = subprocess.run(["ping", "-n", "1", "-w", "200", ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return ip, res.returncode == 0

def main():
    print("Scanning 192.168.0.0/24 subnet...")
    alive = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        for ip, is_alive in ex.map(ping, range(1, 255)):
            if is_alive:
                alive.append(ip)
    print("Alive IPs:", alive)
    
    res = subprocess.run(["arp", "-a"], capture_output=True, text=True)
    print("ARP Table:\n", res.stdout)

if __name__ == "__main__":
    main()
