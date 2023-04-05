
class Saver:
    """
    A class which takes the content of a json or binary file
    (pdf, doc, etc.), and saves it using a certain method.
    ...
    Methods
    -------
    save_json(path = string, data = response)
        Calls each Saver Objects save_json method
        and saves the file in the appropriate way
    
    save_binary(path = string, data, = response.content)
    """
    def __init__(self, savers=None) -> None:
        self.savers = savers

    def save_json(self, path, data):
        for saver in self.savers:
            saver.save_json(path, data)

    def save_binary(self, path, data):
        for saver in self.savers:
            saver.save_binary(path, data)

    # def save_extracted_text(self, path, data):
    #     return 0
