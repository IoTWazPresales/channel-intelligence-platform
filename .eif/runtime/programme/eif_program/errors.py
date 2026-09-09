from eif_reason_codes import is_reason_code


class ProgramError(Exception):
    def __init__(self, code: str, message: str):
        if not is_reason_code(code):
            message = f'unregistered reason {code!r}: {message}'
            code = 'UNKNOWN_REASON_CODE'
        self.code = code
        super().__init__(f'{code}: {message}')
