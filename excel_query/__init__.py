import pandas as pd

class ExcelQueryHandler:
    def __init__(self, excel_path: str):
        self.df = pd.read_excel(excel_path)
