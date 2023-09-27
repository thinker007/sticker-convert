#!/usr/bin/env python3

class FakeCbMsg:
    def __init__(self, msg_protocol=print):
        self.msg_protocol = msg_protocol

    def put(self, msg):
        self.msg_protocol(msg)