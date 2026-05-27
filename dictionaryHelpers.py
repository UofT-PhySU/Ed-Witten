import csv 
import numpy as np

def get_dict(filename):
    """Reads a csv file and returns a dictionary of the data
    Args:
        filename (str): name of the csv file
     Returns:
        quotes_dict (dict): dictionary of the data contained in the csv file
    """
    with open(filename, "r") as q:
        reader = csv.reader(q, delimiter="|")
        first = True
        quotes_dict = {}
        for row in reader:
            row = list(map(strip_space_both_ends, row))
            if first == True:
                header = row
                first = False
                for j in range(0, len(header)):
                    quotes_dict[f'{header[j]}'] = []
            else:
                for j in range(len(row)):
                    quotes_dict[f'{header[j]}'].append(row[j])
    return quotes_dict
   

def save_dict(slist:dict, filename):
    """Saves a dictionary to a csv file
    Args:
        slist (dict): dictionary to be saved
    Returns:
        None
    """
    delim = '|'
    keyslist = list(slist.keys())
    fkey = keyslist[0]  
    keysstring = delim.join(keyslist)

    with open(filename, 'w') as q:
        print(keysstring, file=q)
        if len(slist) != 0:
            for i in range(len(slist[fkey])):
                line = []
                for headers in slist:
                    try:
                        line.append(slist[f'{headers}'][i])
                    except:
                        print("There was an issue with appending things")
                print(delim.join(line),file=q)


def makeDisplayMessage(dictionary, listOfKeys, boxsize, delims):
    nmes = int(np.ceil(len(dictionary[listOfKeys[0]])/boxsize))
    mestext = []
    for i in range(nmes):
        mestext.append('```')
    for i in range(len(dictionary[listOfKeys[0]])):
        num = i + 1
        temp = '\n' + str(num) +') ' 
        for j in range(len(listOfKeys)):
            temp += dictionary[listOfKeys[j]][i] + " " + delims[j] + " "
        mestext[int(np.floor((num - 1)/boxsize))] += temp
    return mestext


def truncationIndices(myList, myKey):
    outList = []
    for j in range(len(myList)):
        if myKey.lower() in myList[j].lower():
            outList.append(j)
    return outList


def truncateDict(myDict, indices):
    theKeys = list(myDict.keys())
    if len(indices) == 0:
        return {theKeys[j]:[] for j in range(len(theKeys))}
    return {theKeys[j]:[myDict[theKeys[j]][ii] for ii in indices] for j in range(len(theKeys))}


def removeIndex(myDict, nth):
    sampleKey = list(myDict.keys())[0]
    overallLength = len(myDict[sampleKey])
    missingIndices = np.zeros(overallLength - 1, dtype=int)
    counter = int(0)
    for j in range(overallLength):
        if j != nth:
            missingIndices[counter] = j
            counter += 1
    return truncateDict(myDict, missingIndices)


def mergeTwoDictionaries(dict1, dict2):
    outDict = dict1
    for key in outDict.keys():
        for ss in dict2[key]:
            outDict[key].append(ss)
    return outDict


def removeMultipleFromDict(myDict, removedIndices):
    if len(removedIndices) == 0:
        return myDict
    sampleKey = list(myDict.keys())[0]
    overallLength = len(myDict[sampleKey])

    outIndices = np.zeros(overallLength - len(removedIndices), dtype=int)
    counter = 0
    for j in range(overallLength):
        if j not in removedIndices:
            outIndices[counter] = int(j)
            counter += 1
    return truncateDict(myDict, outIndices)


def strip_space_both_ends(text:str):
    """Removes spaces from the beginning and end of a string
    Args:
        text (str): string to be stripped
    
    Returns:
        text (str): string with spaces removed from the beginning and end
    """
    while True:
        if text[0] == ' ':
            new_text = text[1:]
        elif text[-1] == ' ':
            new_text = text[:-1]
        else: 
            break
        text = new_text
    return text

