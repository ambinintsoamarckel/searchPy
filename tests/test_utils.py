# tests/test_utils.py

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_test_name(name):
    """Affiche le nom d'un test en cours."""
    print(f"\\n{bcolors.HEADER}===== RUNNING TEST: {name} ====={bcolors.ENDC}")

def print_test_result(name, passed=True):
    """Affiche le résultat d'un test."""
    if passed:
        print(f"{bcolors.OKGREEN}===== TEST PASSED: {name} ====={bcolors.ENDC}")
    else:
        print(f"{bcolors.FAIL}===== TEST FAILED: {name} ====={bcolors.ENDC}")
