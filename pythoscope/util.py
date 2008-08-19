def read_file_contents(filename):
    fd = file(filename)
    contents = fd.read()
    fd.close()
    return contents
