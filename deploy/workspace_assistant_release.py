"""Interactive, credential-free SSH release helper for the KTP workbench."""
import getpass
import json
import shlex
import sys
import paramiko

client = paramiko.SSHClient()
client.load_system_host_keys()
password = getpass.getpass("SSH password: ")
client.connect("172.27.127.3", username="yuehao", password=password, look_for_keys=False, allow_agent=False, timeout=20)
print("CONNECTED", flush=True)
try:
    for line in sys.stdin:
        item = json.loads(line)
        if item.get("exit"):
            break
        if "put" in item:
            with client.open_sftp() as sftp:
                sftp.put(item["put"], item["target"])
            print("UPLOADED", flush=True)
        elif "cmd" in item:
            command = item["cmd"]
            stdin, stdout, stderr = client.exec_command(command, timeout=item.get("timeout", 120))
            if item.get("sudo"):
                stdin.write(password + "\n")
                stdin.flush()
            print(stdout.read().decode("utf-8", errors="replace"), flush=True)
            print(stderr.read().decode("utf-8", errors="replace"), flush=True)
            print("EXIT", stdout.channel.recv_exit_status(), flush=True)
finally:
    client.close()
