from struct import pack, unpack
from functools import reduce
from time import time


class PacketWorker:
    def __init__(self, data=None):
        self.data = data

    def pack(self, data=None):
        packet = b""
        if data != b'\xc0\x0c':
            if data is not None:
                domains = data.split(".")
            else:
                domains = self.data.split(".")
            for domain in domains:
                packet += str(chr(len(domain))).encode("utf-8")
                packet += domain.encode("utf-8")
            packet += str(chr(0)).encode("utf-8")
        else:
            packet += data
        return packet

    def unpack(self, data, raw):
        domain = ""
        while data[0] != 0:
            if data[0] & 192 == 192:
                offset = unpack("!H", data[:2])[0] & 16383
                data = data[2:]
                domain += self.unpack(raw[offset:], raw)[0]
                return domain, data, b"\xc0\x0c"
            else:
                count = data[0]
                for i in range(1, count + 1):
                    domain += chr(data[i])
                domain += '.'
                data = data[count + 1:]
        return domain[:-1], data[1:], b""


class HeaderQuery:
    def __init__(
            self,
            identification=None,
            flags=None,
            responses_count=0,
            answers_count=0,
            resources_count=0,
            optional_count=0):
        self.identification = identification
        self.flags = flags
        self.responses_count = responses_count
        self.answers_count = answers_count
        self.resources_count = resources_count
        self.optional_count = optional_count

    def unpack(self, header_information):
        (self.identification,
         self.flags,
         self.responses_count,
         self.answers_count,
         self.resources_count,
         self.optional_count) = unpack("!HHHHHH", header_information[:12])
        return header_information[12:]

    def pack(self):
        header_information = pack(
            "!HHHHHH",
            self.identification,
            self.flags,
            self.responses_count,
            self.answers_count,
            self.resources_count,
            self.optional_count)
        return header_information

    def __str__(self):
        return f"Header: ID:{self.identification} FLAGS:{self.flags} " \
               f"NUM_OF_RESP:{self.responses_count} NUM_OF_ANS:{self.answers_count} " \
               f"NUM_OF_VALID:{self.resources_count} NUM_OF_OPT:{self.optional_count}"


class StandardQuery:
    INTERNET_QUESTION_RESPONSE = 1
    DEFAULT_QUESTION_TYPE = 255

    def __init__(
            self,
            q_name=None,
            q_type=DEFAULT_QUESTION_TYPE,
            q_class=INTERNET_QUESTION_RESPONSE):
        self.type = q_type
        self.q_class = q_class
        self.packer = PacketWorker()
        self.ptr = b""
        if q_name is not None:
            self.name = PacketWorker.pack(q_name)

    def unpack(self, data, raw):
        self.name, data, self.ptr = self.packer.unpack(data, raw)
        self.type, self.q_class = unpack("!hh", data[:4])
        return data[4:]

    def pack(self):
        if self.ptr != b"":
            self.name = self.ptr
        return self.packer.pack(self.name) + pack("!hh", self.type, self.q_class)

    def __str__(self):
        return f"QUEST: NAME:{self.name} TYPE:{self.type} CLASS:{self.q_class}"


class DNSMessage:
    def __init__(
            self,
            header=HeaderQuery(),
            query=None,
            answers=None):
        self.header = header
        self.query = query
        self.answers = answers
        self.validation = []

    def pack(self):
        data = b""
        data += self.header.pack()
        data += reduce(lambda res, x: res + x.pack(), self.query, b"")
        data += reduce(lambda res, x: res + x.pack(), self.answers, b"")
        return data

    def unpack(self, data):
        raw = data
        data = self.header.unpack(data)
        self.query = []
        self.answers = []
        self.validation = []
        for index in range(self.header.responses_count):
            query = StandardQuery()
            data = query.unpack(data, raw)
            self.query.append(query)
        for index in range(self.header.answers_count):
            resource_record = ResourceRecord()
            data = resource_record.unpack(data, raw)
            self.answers.append(resource_record)
        for index in range(self.header.optional_count):
            resource_record = ResourceRecord()
            data = resource_record.unpack(data, raw)
            self.validation.append(resource_record)
        return data

    def __str__(self):
        res = "MESSAGE:\n"
        res += str(self.header)
        for query_item in self.query:
            res += '\n{}'.format(str(query_item))
        for answer in self.answers:
            res += '\n{}'.format(str(answer))
        return res


class ResourceRecord:
    def __init__(
            self,
            all_info=None,
            owner_name=None,
            type=None,
            type_class=None,
            ttl=0):
        self.owner = owner_name
        self.type = type
        self.type_class = type_class
        self.TTL = ttl
        self.length_of_data = None
        self.data = None
        self.expected = int(time()) + ttl
        self.packer = PacketWorker()
        self.used = False
        self.oneOff = ttl == 0
        self.ptr = b""
        self.all_info = all_info

    def pack(self):
        data = b""
        if self.ptr != b"":
            self.owner = self.ptr
        data += self.packer.pack(self.owner) + pack("!h", self.type) + \
            pack("!h", self.type_class) + pack("!I", max(0, self.expected - int(time()))) + \
            pack("!H", self.length_of_data) + self.data
        return data

    def unpack(self, data, raw):
        self.owner, data, self.ptr = self.packer.unpack(data, raw)
        self.type, self.type_class, self.TTL, self.length_of_data = unpack("!hhiH", data[:10])
        self.oneOff = self.TTL == 0
        self.expected = int(time()) + self.TTL
        data = data[10:]
        self.data = data[:self.length_of_data]
        data = data[self.length_of_data:]
        self.all_info = data
        return data

    def __str__(self):
        return f"Resource Record: OWNER:{self.owner} " \
               f"TYPE:{self.type} CLASS:{self.type_class} " \
               f"USED:{self.used} EXPECT:{self.expected} " \
               f"LENGTH:{self.length_of_data}"
