class ExceptionWithMessage(Exception):
    def __init__(self, message):
        self.message = message

class FilenameException(ExceptionWithMessage):
    pass
