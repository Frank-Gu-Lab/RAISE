import numpy as np
from typing import Dict, List, Tuple


class Reagent:
    def __init__(self, name: str, conc_range: List[float] | None):
        self.name = name
        if conc_range is not None:
            self.set_concentration_range(conc_range=conc_range)

    def set_concentration_range(self, conc_range: List[float]):
        self.conc_range = np.array(sorted(conc_range))
        self.conc_max = self.conc_range[-1]
    
    def get_concentration_range(self) -> np.ndarray[float]:
        return self.conc_range

    def get_max_conc(self) -> float:
        return self.conc_max
    
    def get_stock_concentration(self, target_conc: float):
        conc_range: np.ndarray[float] = self.get_concentration_range()
        mask = conc_range >= target_conc
        if np.sum(mask) == 0:
            return None
        idx = np.argmax(mask)
        return conc_range[idx]

    def get_formulation(self, target_conc: float, stock_conc: float, target_vol: float):
        if target_conc > 0 and target_vol == 0:
            return None, None
        
        if target_conc == 0:
            return {f'{self.name}': 0, 'H2O': target_vol}, 1
        
        # print(f'Target Conc: {target_conc}, Stock Conc: {stock_conc}, Target Vol: {target_vol}')

        dilution_factor: float = stock_conc / target_conc
        scaling_factor: float = target_vol / dilution_factor

        volumes = np.array([1, dilution_factor - 1]) * scaling_factor
        #volumes = np.round(volumes, 3)

        if dilution_factor > 1:
            non_target_dilution_factor = 1 + 1 / (dilution_factor - 1)
        else:
            non_target_dilution_factor = 1

        result_formulation = {(self.name, str(float(stock_conc))): volumes[0], 'H2O': volumes[1]}

        return {k: round(v, 2) for k, v in result_formulation.items()}, non_target_dilution_factor

def get_mixture_formulation(reagent_dict: Dict[str, Reagent], target_concs: Dict[str, float], total_volume: float = 200.0) -> Dict[str, float] | None:
    if target_concs == {}:
        return {('H2O', str(100.0)): total_volume}
    
    if target_concs == {'H2O': 100.0}:
        return {('H2O', str(100.0)): total_volume}
    
    for k in target_concs.keys():
        assert k in reagent_dict
    
    formulation_final: Dict[str, float] = dict()
    volume: float = total_volume

    for (reagent_name, target_conc) in (target_concs.copy()).items():
        if target_conc == 0.0:
            target_concs.pop(reagent_name)
    
    if target_concs == {}:
        return {('H2O', str(100.0)): total_volume}
    
    volume_partition: float = total_volume / len(target_concs)
    volume_H2O: float = 0.0
    for i, (reagent_name, target_conc) in enumerate(target_concs.items(), start=1):
        target_conc = target_conc * len(target_concs)
        reagent_curr: Reagent = reagent_dict.get(reagent_name)
        reagent_stock_conc: float = reagent_curr.get_stock_concentration(target_conc)
        if reagent_stock_conc is None:
            print(f'No Stock Solution Available: {target_conc}')
            return None
        print(f'{i}) {reagent_name}: {str(float(reagent_stock_conc))}')

        formulation_curr, _ = reagent_curr.get_formulation(target_conc, reagent_stock_conc, volume_partition)
        #print(formulation_curr)
        if formulation_curr is None:
            print(f'Cannot Mix Stock Solutions to Reach Target Concentrations in {volume}uL.')
            return None

        if 'H2O' in formulation_curr:
            volume_H2O += formulation_curr.pop('H2O')

        formulation_final.update(formulation_curr)

    formulation_final[('H2O', str(100.0))] = volume_H2O
    assert len(formulation_final) > 0
    return formulation_final
    

def get_max_concentrations(reagent1: Reagent, reagent2: Reagent, target_conc1: float):
    volume: float = 100
    #max_conc_1: float = reagent1.get_max_conc() - precision
    r1_formulation, _ = reagent1.get_formulation(target_conc1, reagent1.get_max_conc(), volume)

    volume_remaining: float = r1_formulation.pop('H2O')
    max_conc_2: float = round(reagent2.get_max_conc() * volume_remaining / volume, 3)

    return {f'{reagent1.name}_{reagent1.get_max_conc()}': target_conc1, 
            f'{reagent2.name}_{reagent2.get_max_conc()}': max_conc_2}

def is_formulation_possible(reagent1: Reagent, reagent2: Reagent, target_conc1: float, target_conc2: float) -> bool:
    max_concentrations: Dict[str, float] = get_max_concentrations(reagent1, reagent2, target_conc1)
    return target_conc2 <= max_concentrations[f'{reagent2.name}_{reagent2.get_max_conc()}']


if __name__ == "__main__":
    reagent_1 = Reagent('SDS', [4])
    reagent_2 = Reagent('Ethanol', [100])
    #print(reagent_1.get_formulation(2, 4, 100))
    conc_1 = 1
    conc_2 = 75
    volume = 200
    counter = 1
    for i in np.arange(0, 75.1, 5):
        for j in np.arange(0.05, 1.01, 0.05):
            result = get_mixture_formulation({'Ethanol': reagent_2, 'SDS': reagent_1}, {'Ethanol': i, 'SDS': j}, volume)
            if result is None:
                raise ValueError
            else:
                print(counter)
                print(result)
            counter += 1

