from configparser import RawConfigParser

def get_or_create(file_name, section, fields):
    config = RawConfigParser()
    read_result = config.read(file_name)
    for (field_name, field_prompt) in fields:
        if section not in config or field_name not in config[section]:
            config_value = ''
            while not config_value.strip():
                config_value = input(field_prompt)
            config[section][field_name] = config_value
    with open(file_name, 'w') as config_file:
        config.write(config_file)
    read_result = config.read(file_name)
    return config[section]