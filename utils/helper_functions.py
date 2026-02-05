from baybe.parameters import NumericalDiscreteParameter, CategoricalParameter, SubstanceParameter, NumericalContinuousParameter
from typing import List, Dict
import pandas as pd


def parameter_creator(input_dictionary: Dict) -> List:
    '''
    creates a list of parameter objects for baybe optimizer

    accepts a dictionary of parameter descriptions
    return as list of paramter objects
    '''

    parameters = []


    for keys in input_dictionary.keys():

        working_key = input_dictionary[keys]

        if working_key['Type'] == 'Categorical':
            
            #probably add a chunk here that checks for optional args - if not included specify the defaults

            parameter = CategoricalParameter(
                name = working_key['Name'],
                values = working_key['Values'],
                encoding = working_key['Encoding']
                )
        elif working_key['Type'] == 'NumericalDiscrete':

            parameter = NumericalDiscreteParameter(
                name = working_key['Name'],
                values = working_key['Values']
                )
            
        elif working_key['Type']=='Substance':
            
            parameter = SubstanceParameter(
                name = working_key['Name'],
                data = working_key['Data'],
                encoding = working_key['Encoding']
            )

        elif working_key['Type'] == 'NumericalContinuous':
            parameter = NumericalContinuousParameter(
                name = working_key['Name'],
                bounds= working_key['Bounds']
            )
            
        else:
            raise(ValueError('Unsupported Optimization Parameter'))
        
        parameters.append(parameter)


    return parameters


def target_creator(target_dictionary: Dict) -> List:

    targets = []
    

    for keys in target_dictionary.keys():

        working_key = target_dictionary[keys]


    return targets