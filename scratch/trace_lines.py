from html.parser import HTMLParser

class LineTracer(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        elem_id = attr_dict.get('id', '')
        pos = self.getpos()
        if 550 <= pos[0] <= 1938:
            if elem_id.startswith('view-'):
                print(f"\n--- LINE {pos[0]}: {elem_id} ---")
                print(f"Current open stack (depth {len(self.stack)}):")
                for item in self.stack:
                    print(f"  <{item[0]} id='{item[1]}'> (opened at line {item[2]})")
        self.stack.append((tag, elem_id, pos[0]))

    def handle_endtag(self, tag):
        if self.stack:
            self.stack.pop()

if __name__ == '__main__':
    parser = LineTracer()
    with open('frontend/index.html', 'r', encoding='utf-8') as f:
        parser.feed(f.read())
