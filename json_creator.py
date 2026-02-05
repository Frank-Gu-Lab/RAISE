import json
from typing import Callable, Dict, List

# Maybe change name of this function later...
def get_function(expression: str) -> Callable[[int], int]:
    substrings: List[str] = expression.split('=')
    assert len(substrings) == 2
    arg: int = int(substrings[1])
    return lambda x: x + arg

def load_labware_usage_parameters(fname: str) -> Dict[str, int | Callable[[int], int]]:
    with open(fname, mode='r') as fd:
        lw_usage_dict: Dict[str, int | str] = json.load(fd)
    
    for param_name, value in lw_usage_dict.items():
        if isinstance(value, str):
            lw_usage_dict[param_name] = get_function(value)
    return lw_usage_dict

if __name__ == '__main__':
    lw_usage = load_labware_usage_parameters('./PARAMETERS/RAISE_STATIC_CA_LABWARE_USAGE.json')
    for param_name, value in lw_usage.items():
        print(param_name)
        if not isinstance(value, int):
            for i in range(10):
                print(value(i))
        else:
            print(value)