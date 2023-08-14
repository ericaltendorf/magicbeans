class TextRenderer():
    def __init__(self, file) -> None:
        """Initialize with the file to write to."""
        self.file = file

    # TODO: parameterize the width of this header, probably
    # via an argument on ReportDriver.
    def subreport_header(self, title: str, q: str = None):
        # TODO: move this into ReportDriver?
        result = " " + ("_" * 140) + f" \n|{title:_^140}|\n"
        if q:
            # Text wrapping is useful if you're consuming as a text file;
            #   if you convert to PDF that will wrap for you.
            # result += "\n".join(textwrap.wrap(q, width=140,
            #       initial_indent="", subsequent_indent="  ")) + "\n"
            result += q + "\n"
        self.file.write(result)