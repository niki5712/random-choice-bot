import re


def escape(text):
    return re.sub(
        pattern=r'[\\_*[\]()~`>#+\-=|{}.!]',
        repl=lambda match_object: rf'\{match_object.group()}',
        string=text
    )
