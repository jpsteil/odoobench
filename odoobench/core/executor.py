"""
Connection Executor abstraction for OdooBench
Provides a unified interface for executing commands on local or remote machines
"""

import subprocess
import os
from abc import ABC, abstractmethod
from typing import Iterator, Optional, Tuple
import paramiko
from io import StringIO


class ConnectionExecutor(ABC):
    """Abstract base class for executing commands on local or remote machines"""

    @abstractmethod
    def run_command(self, cmd: str, timeout: int = 30) -> Tuple[str, str, int]:
        """
        Execute a command and return (stdout, stderr, exit_code)

        Args:
            cmd: The command to execute
            timeout: Command timeout in seconds

        Returns:
            Tuple of (stdout, stderr, exit_code)
        """
        pass

    @abstractmethod
    def read_file(self, path: str) -> str:
        """
        Read the contents of a file

        Args:
            path: Absolute path to the file

        Returns:
            File contents as string
        """
        pass

    @abstractmethod
    def write_file(self, path: str, content: str) -> bool:
        """
        Write content to a file

        Args:
            path: Absolute path to the file
            content: Content to write

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def file_exists(self, path: str) -> bool:
        """Check if a file exists"""
        pass

    @abstractmethod
    def dir_exists(self, path: str) -> bool:
        """Check if a directory exists"""
        pass

    @abstractmethod
    def tail_file(self, path: str, lines: int = 100) -> str:
        """
        Get the last N lines of a file

        Args:
            path: Absolute path to the file
            lines: Number of lines to return

        Returns:
            Last N lines of the file
        """
        pass

    @abstractmethod
    def tail_file_follow(self, path: str, callback) -> None:
        """
        Follow a file (like tail -f) and call callback with new lines

        Args:
            path: Absolute path to the file
            callback: Function to call with each new line
        """
        pass

    @abstractmethod
    def stop_tail(self) -> None:
        """Stop any running tail follow operation"""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the connection is still active"""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection"""
        pass

    def get_file_size(self, path: str) -> int:
        """Get file size in bytes"""
        stdout, stderr, code = self.run_command(f"stat -c%s '{path}' 2>/dev/null || stat -f%z '{path}'")
        if code == 0 and stdout.strip():
            return int(stdout.strip())
        return 0

    def list_directory(self, path: str) -> list:
        """List files in a directory"""
        stdout, stderr, code = self.run_command(f"ls -la '{path}'")
        if code == 0:
            return stdout.strip().split('\n')
        return []


class LocalExecutor(ConnectionExecutor):
    """Execute commands on the local machine"""

    def __init__(self):
        self._tail_running = False

    def run_command(self, cmd: str, timeout: int = 30) -> Tuple[str, str, int]:
        """Execute a command locally"""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "Command timed out", -1
        except Exception as e:
            return "", str(e), -1

    def read_file(self, path: str) -> str:
        """Read a local file"""
        try:
            with open(path, 'r') as f:
                return f.read()
        except Exception as e:
            raise IOError(f"Failed to read file {path}: {e}")

    def write_file(self, path: str, content: str) -> bool:
        """Write to a local file"""
        try:
            with open(path, 'w') as f:
                f.write(content)
            return True
        except Exception as e:
            raise IOError(f"Failed to write file {path}: {e}")

    def file_exists(self, path: str) -> bool:
        """Check if local file exists"""
        return os.path.isfile(path)

    def dir_exists(self, path: str) -> bool:
        """Check if local directory exists"""
        return os.path.isdir(path)

    def tail_file(self, path: str, lines: int = 100) -> str:
        """Get last N lines of a local file"""
        stdout, stderr, code = self.run_command(f"tail -n {lines} '{path}'")
        if code == 0:
            return stdout
        raise IOError(f"Failed to tail file {path}: {stderr}")

    def tail_file_follow(self, path: str, callback) -> None:
        """Follow a local file with tail -f"""
        import threading

        self._tail_running = True

        def follow():
            try:
                process = subprocess.Popen(
                    ['tail', '-f', path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                self._tail_process = process

                while self._tail_running:
                    line = process.stdout.readline()
                    if line:
                        callback(line.rstrip('\n'))
                    elif process.poll() is not None:
                        break

                process.terminate()
            except Exception as e:
                callback(f"Error following file: {e}")

        self._tail_thread = threading.Thread(target=follow, daemon=True)
        self._tail_thread.start()

    def stop_tail(self) -> None:
        """Stop the tail follow operation"""
        self._tail_running = False
        if hasattr(self, '_tail_process') and self._tail_process:
            try:
                self._tail_process.terminate()
            except:
                pass

    def is_connected(self) -> bool:
        """Local is always connected"""
        return True

    def disconnect(self) -> None:
        """Nothing to disconnect for local"""
        self.stop_tail()


class SSHExecutor(ConnectionExecutor):
    """Execute commands on a remote machine via SSH.

    Connections are opened and closed per operation (no persistent connection).
    """

    def __init__(self, host: str, port: int = 22, username: str = None,
                 password: str = None, key_path: str = None):
        """
        Initialize SSH executor (does not connect yet).

        Args:
            host: Remote hostname or IP
            port: SSH port (default 22)
            username: SSH username
            password: SSH password (if using password auth)
            key_path: Path to SSH private key (if using key auth)
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_path = key_path
        self._tail_running = False
        self._tail_client = None  # Only for tail_file_follow

    def _create_client(self) -> paramiko.SSHClient:
        """Create and connect a new SSH client."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            'hostname': self.host,
            'port': self.port,
            'username': self.username,
        }

        if self.key_path:
            connect_kwargs['key_filename'] = self.key_path
        elif self.password:
            connect_kwargs['password'] = self.password

        client.connect(**connect_kwargs)
        return client

    def run_command(self, cmd: str, timeout: int = 30) -> Tuple[str, str, int]:
        """Execute a command remotely via SSH (connects and disconnects)."""
        client = None
        try:
            client = self._create_client()
            stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)

            exit_code = stdout.channel.recv_exit_status()
            stdout_text = stdout.read().decode('utf-8', errors='replace')
            stderr_text = stderr.read().decode('utf-8', errors='replace')

            return stdout_text, stderr_text, exit_code
        except Exception as e:
            return "", str(e), -1
        finally:
            if client:
                client.close()

    def read_file(self, path: str) -> str:
        """Read a remote file via SFTP (connects and disconnects)."""
        client = None
        try:
            client = self._create_client()
            sftp = client.open_sftp()
            with sftp.open(path, 'r') as f:
                content = f.read().decode('utf-8', errors='replace')
            sftp.close()
            return content
        except Exception as e:
            raise IOError(f"Failed to read remote file {path}: {e}")
        finally:
            if client:
                client.close()

    def write_file(self, path: str, content: str) -> bool:
        """Write to a remote file via SFTP (connects and disconnects)."""
        client = None
        try:
            client = self._create_client()
            sftp = client.open_sftp()
            with sftp.open(path, 'w') as f:
                f.write(content.encode('utf-8'))
            sftp.close()
            return True
        except Exception as e:
            raise IOError(f"Failed to write remote file {path}: {e}")
        finally:
            if client:
                client.close()

    def file_exists(self, path: str) -> bool:
        """Check if remote file exists"""
        stdout, stderr, code = self.run_command(f"test -f '{path}' && echo 1 || echo 0")
        return stdout.strip() == '1'

    def dir_exists(self, path: str) -> bool:
        """Check if remote directory exists"""
        stdout, stderr, code = self.run_command(f"test -d '{path}' && echo 1 || echo 0")
        return stdout.strip() == '1'

    def tail_file(self, path: str, lines: int = 100) -> str:
        """Get last N lines of a remote file"""
        stdout, stderr, code = self.run_command(f"tail -n {lines} '{path}'")
        if code == 0:
            return stdout
        raise IOError(f"Failed to tail remote file {path}: {stderr}")

    def tail_file_follow(self, path: str, callback) -> None:
        """Follow a remote file with tail -f.

        Note: This keeps a connection open while following. Call stop_tail() to close.
        """
        import threading

        self._tail_running = True

        def follow():
            client = None
            channel = None
            try:
                client = self._create_client()
                self._tail_client = client  # Store for stop_tail
                transport = client.get_transport()
                channel = transport.open_session()
                channel.exec_command(f"tail -f '{path}'")

                buffer = ""
                while self._tail_running:
                    if channel.recv_ready():
                        data = channel.recv(4096).decode('utf-8', errors='replace')
                        buffer += data
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            callback(line)
                    elif channel.exit_status_ready():
                        break
                    else:
                        import time
                        time.sleep(0.1)

            except Exception as e:
                if self._tail_running:  # Only report if not intentionally stopped
                    callback(f"Error following remote file: {e}")
            finally:
                if channel:
                    try:
                        channel.close()
                    except:
                        pass
                if client:
                    try:
                        client.close()
                    except:
                        pass
                self._tail_client = None

        self._tail_thread = threading.Thread(target=follow, daemon=True)
        self._tail_thread.start()

    def stop_tail(self) -> None:
        """Stop the tail follow operation and close its connection."""
        self._tail_running = False
        if self._tail_client:
            try:
                self._tail_client.close()
            except:
                pass
            self._tail_client = None

    def is_connected(self) -> bool:
        """Check if there's an active tail connection."""
        return self._tail_client is not None

    def disconnect(self) -> None:
        """Stop any active operations."""
        self.stop_tail()


def create_executor(connection_config: dict) -> ConnectionExecutor:
    """
    Factory function to create the appropriate executor based on connection config

    Args:
        connection_config: Dictionary with connection details
            - For local: {'is_local': True} or {'host': 'localhost', 'username': None}
            - For SSH: {'host': 'server', 'port': 22, 'username': 'user', ...}

    Returns:
        ConnectionExecutor instance (LocalExecutor or SSHExecutor)
    """
    # Check if this is a local connection
    is_local = connection_config.get('is_local', False)
    host = connection_config.get('host', 'localhost')
    username = connection_config.get('username')

    # If explicitly local, or localhost without username, use LocalExecutor
    if is_local or (host in ('localhost', '127.0.0.1') and not username):
        return LocalExecutor()

    # Otherwise use SSH
    return SSHExecutor(
        host=host,
        port=connection_config.get('port', 22),
        username=username,
        password=connection_config.get('password'),
        key_path=connection_config.get('key_path') or connection_config.get('ssh_key_path')
    )
