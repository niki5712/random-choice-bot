import re

from config import USERNAME, COMMENT_PREFIX


search_bot_mention = re.compile(fr'\B@{USERNAME}(?:\s+l(?P<limit>\d+))?\b').search
match_order = re.compile(r'(?!{}).+'.format(re.escape(COMMENT_PREFIX)))
