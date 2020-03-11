import os
import sys
from jinja2 import Environment, FileSystemLoader

def fill_template(template_path, destination_dir):
    basename = os.path.basename(template_path)
    env = Environment(loader=FileSystemLoader(os.path.dirname(template_path)))
    template = env.get_template(basename)

    params = {}
    params['celery'] = os.environ['CELERY']
    params['logdir'] = os.environ['LOGDIR']
    params['app_root'] = os.environ['APP_ROOT']
    socket_name = input('Enter the name for the unix socket you will be using to connect the host machine to '
                          'the Docker container.  This should be named in your nginx conf. '
                          'Note-- just the filename, not a full path. Enter: ')
    params['socket_name'] = socket_name

    with open(os.path.join(destination_dir, basename), 'w') as outfile:
        outfile.write(template.render(params))


if __name__ == '__main__':
    destination_dir = sys.argv[1]
    file_list = sys.argv[2:]
    for f in file_list:
        fill_template(f, destination_dir)
