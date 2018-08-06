import matplotlib.pyplot as plt
import matplotlib.colors as cl
import numpy as np
import pandas as pd
from os import listdir
from os.path import isfile, join


def csv_to_graph(dir_path):
    """Merge and convert csv file(s) with fixed and shared x-axis
    in specified directory.
    """
    # Get files in directory.
    files = [f for f in listdir(dir_path) if isfile(join(dir_path, f))]

    # Construct data frame.
    df = {'epoch' : range(300)}
    # Extract Data
    for file in files:
        df[file[:-4]] = pd.read_csv(dir_path+'/'+file)['Value']
    df = pd.DataFrame(df)

    # Use generator instead to save space?
    # TODO: Need more contrast between bg and lines?
    # colours = [name for name, _ in cl.cnames.items()]
    # DARK BACKGROUND
    # plt.style.use('dark_background')
    # colours = ['g', 'r', 'c', 'm', 'y', 'k', 'w']
    # LIGHT BACKGROUND
    colours = ['b', 'g', 'r', 'c', 'm', 'y', 'k']

    # Plot!
    for i in range(len(files)):
        plt.plot('epoch', files[i][:-4], data=df, marker='o', linewidth=1,
                 markersize=1, color=colours[i], label=files[i][:-4])
    plt.legend()
    plt.show()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file', help='input directory')

    args = parser.parse_args()

    csv_to_graph(args.file)

