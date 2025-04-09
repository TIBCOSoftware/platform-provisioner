from utils.color_logger import ColorLogger
from utils.env import ENV

class PageObjectGlobal:
    def __init__(self, page):
        self.page = page
        self.env = ENV

    def goto_left_navbar(self, item_name):
        ColorLogger.info(f"Going to left side menu ...")
        self.page.locator(".nav-bar-pointer", has_text=item_name).wait_for(state="visible")
        self.page.locator(".nav-bar-pointer", has_text=item_name).click()
        print(f"Clicked left side menu '{item_name}'")
        self.page.wait_for_timeout(500)
