import matplotlib.pyplot as plt
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

    # Plot!
    for file in files:
        plt.plot('epoch', file[:-4], data=df, marker='o', linewidth=1, markersize=1, color='skyblue', label=file[:-4])
    plt.legend()
    plt.show()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file', help='input directory')

    args = parser.parse_args()

    csv_to_graph(args.file)

