import configparser


def load_config(config_filepath, config_sections=[]):
    '''
    config_filepath is the path to a config/ini file
    config_sections is a list of names for sections in that file
    if None, then just return the [DEFAULT] section
    '''

    config = configparser.ConfigParser()
    config.read(config_filepath)
    main_dict = {}
    for key in config[config.default_section]:
        main_dict[key] =  config[config.default_section][key]

    d = {}
    for config_section in config_sections:
        if config_section in config:
            d1 = {}
            for key in config[config_section]:
                d1[key] =  config[config_section][key]
            keys_intersection = set(d1.keys()).intersection(set(d.keys()))
            if ((len(keys_intersection)==0) 
                 or 
                (set(main_dict.keys()) == keys_intersection)):
                d.update(d1)
            else:
                raise Exception('Config variable collision with variables %s.  '
                    'Check that the variables defined in section %s '
                    'do not match any in other sections of the %s file'
                    % (keys_intersection, config_section, config_filepath)
                )
        else:
            raise configparser.NoSectionError()
    main_dict.update(d)
    return main_dict


def read_general_config(config_filepath, additional_sections=[]):
    '''
    This loads the "main" config file.  We have this function since
    the configuration depends on environment parameters.
    '''
    config_dict = load_config(config_filepath, additional_sections)

    # Based on the choice for the compute environment, read those params also:
    try:
        compute_env = config_dict['cloud_environment']
    except KeyError as ex:
        raise Exception('Your configuration file needs to define a variable named %s which indicates the cloud provider' % ex)

    config_dict.update(load_config(config_filepath, [compute_env,]))

    return config_dict
