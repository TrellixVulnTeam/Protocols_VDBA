from socket import *
import datetime
import asyncio
import argparse
from dns_packets import *
import pickle


def get_args():
    parser = argparse.ArgumentParser(description="DNS server")
    parser.add_argument(
        "forwarder",
        default="8.8.4.4",
        help="Forwarder IP address")
    parser.add_argument(
        "--port",
        help="Port",
        default=53, type=int)
    parser.add_argument(
        "--ttl",
        help="Time to life data in cache",
        default=3600, type=int)
    args = parser.parse_args()
    return args


class DNSServer(asyncio.Protocol):
    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        dns = DNS(None, None, None)
        answer = dns.get_addr(data)
        while answer is None:
            answer = dns.get_addr(data)
        print('Datagram received')
        self.transport.sendto(answer, addr)


class DNSError(Exception):
    pass


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls)\
                .__call__(*args, **kwargs)
        return cls._instances[cls]


class DNS(object, metaclass=Singleton):
    def __init__(self, forwarder, ttl, cache):
        self.cache = cache
        self.forwarder = forwarder
        self.err_count = 0
        self.ttl = ttl

    def get_addr(self, packet):
        dns_msg = DNSMessage()
        dns_msg.unpack(packet)
        for question in dns_msg.query:
            if question.name in self.cache.keys():
                answer, timestamp = self.cache[question.name]
                now_date = datetime.datetime.now()
                age = now_date - timestamp
                if age.seconds > self.ttl:
                    print('Record is too old, get new data')
                    return self._get_addr(question, dns_msg)
                else:
                    print('Record found in cache')
                    return answer.pack()
            else:
                print('Record is not found')
                return self._get_addr(question, dns_msg)

    def _get_addr(self, question, dns_msg):
        id = dns_msg.header.identification
        flags = dns_msg.header.flags
        header = HeaderQuery(
            identification=id,
            flags=flags,
            responses_count=1,
            answers_count=0,
            resources_count=0,
            optional_count=0)
        msg = DNSMessage(header, [question], [])
        try:
            with socket(AF_INET, SOCK_DGRAM) as new_socket:
                new_socket.settimeout(1)
                new_socket.sendto(msg.pack(), (self.forwarder, 53))
                data, addr = new_socket.recvfrom(1024)
            answer = DNSMessage()
            answer.unpack(data)
            self.cache[question.name] = (
                answer, datetime.datetime.now())
            return data
        except Exception:
            self.err_count = self.err_count + 1
            print('DNS server is not reached', self.err_count)
            if self.err_count > 6:
                self.err_count = 0
                return b''
                # exit('Google is dead')
            elif self.err_count > 5:
                self.forwarder = '8.8.4.4'


def main(args):
    try:
        cache = pickle.load(open('dump', 'rb'))
    except Exception:
        cache = {}
    dns = DNS(args.forwarder, args.ttl, cache)
    loop = asyncio.get_event_loop()
    listen = loop.create_datagram_endpoint(
        DNSServer, local_addr=('127.0.0.1', args.port))
    transport, protocol = loop.run_until_complete(listen)
    try:
        loop.run_forever()
    except DNSError as e:
        print(e)
    except KeyboardInterrupt:
        pickle.dump(dns.cache, open('dump', 'wb'))

    transport.close()
    loop.close()


if __name__ == "__main__":
    # usage: dns_server.py [-h] [--port PORT] [--ttl TTL] forwarder
    args = get_args()
    main(args)
