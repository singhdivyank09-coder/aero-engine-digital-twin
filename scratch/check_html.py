from html.parser import HTMLParser

VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

class StrictHTML5Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.tabs = [
            'view-operator',
            'view-digital-twin',
            'view-engineer',
            'view-playground',
            'view-replay',
            'view-models-datasets',
            'view-gcs-dfcs',
            'view-metrics',
            'view-audit'
        ]
        self.tab_nesting = {}

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        elem_id = attr_dict.get('id', '')
        pos = self.getpos()

        if elem_id in self.tabs:
            rel_stack = [s for s in self.stack if s[0] not in VOID_TAGS]
            self.tab_nesting[elem_id] = {
                'line': pos[0],
                'stack': [(s[0], s[1]) for s in rel_stack]
            }

        if tag not in VOID_TAGS:
            self.stack.append((tag, elem_id, pos[0]))

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if self.stack:
            # find matching start tag from top
            for i in range(len(self.stack)-1, -1, -1):
                if self.stack[i][0] == tag:
                    self.stack = self.stack[:i]
                    break

def run_analysis():
    parser = StrictHTML5Parser()
    with open('frontend/index.html', 'r', encoding='utf-8') as f:
        parser.feed(f.read())

    print("=== HTML5 DOM TREE ANALYSIS ===")
    for tab in parser.tabs:
        info = parser.tab_nesting.get(tab)
        if not info:
            print(f"❌ {tab}: NOT FOUND")
        else:
            stack_ids = [f"{s[0]}#{s[1]}" if s[1] else s[0] for s in info['stack']]
            print(f"Line {info['line']:4d} | {tab:<22} | Stack: {' > '.join(stack_ids)}")

if __name__ == '__main__':
    run_analysis()
