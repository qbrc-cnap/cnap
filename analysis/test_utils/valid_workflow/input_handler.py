def map_inputs(user, all_data, data_name, id_list):
    text_input = all_data[data_name]
    capitalized = text_input.upper()
    return {id_list[0]:capitalized}
