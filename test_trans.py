import sys
from core.translation import translate

def test():
    print("Testing translation:")
    res = translate("How to apply for pension?", "english", "hindi")
    print(res)

if __name__ == "__main__":
    test()
