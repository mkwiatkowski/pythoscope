def before():
    alist = []
    alist.append(1)
    alist.extend([3, 2])
    alist.insert(0, 4)
    alist.pop()
    alist.remove(3)
    alist.sort()
    return alist

def after(alist):
    alist.reverse()
    return alist

def main():
    after(before())
