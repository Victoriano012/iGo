import collections
import osmnx
import pickle
import urllib
import csv
import os
from staticmap import Line, StaticMap, CircleMarker

# Each highway has a vector of all the edges of the graph it goes through and its coordinates
Highway = collections.namedtuple('Highway', 'description, edges, coordinates')
Congestion = collections.namedtuple('Congestion', 'way_id, current, predicted')


def get_graph(GRAPH_FILENAME, PLACE):
    '''
    Returns the digraph of the streets of a city
        getting it from a file if it has already been stored there
        storing it in the file otherwise
    Arguments:
        GRAPH_FILENAME -> filename of the graph (string ended in ".graph")
        PLACE -> name of the city (string)
    Complexity:
        if graph alrady in file -> same as pickle.load
        otherwise -> same as osmnx.graph_from_place
    '''

    try:
        # if it is already loaded in the file, simply return it
        with open(GRAPH_FILENAME, 'rb') as file:
            return pickle.load(file)

    except Exception as e:
        # otherwise download it
        multi_graph = osmnx.graph_from_place(PLACE, network_type='drive', simplify=True)
        graph = osmnx.get_digraph(multi_graph, weight='length')

        # and store it into the file before returning it
        with open(GRAPH_FILENAME, 'wb') as file2:
            pickle.dump(graph, file2)
        return graph


def download_and_build_highways(HIGHWAYS_URL, graph):
    '''
    Returns the highways of a city from the web
    Arguments:
        HIGHWAYS_URL -> url where the highways are (string, link)
        graph -> graph of the city
    Complexity:
        O(n) where n is the number of highways
    '''

    with urllib.request.urlopen(HIGHWAYS_URL) as response:
        # put all the lines of the webpage in a vector
        lines = [line.decode('utf-8') for line in response.readlines()]

        # read them and store them in a vector
        reader = csv.reader(lines, delimiter=',', quotechar='"')
        next(reader)    # ignore first line with description

        highways = []
        for line in reader:
            way_id, description, coordinates = line
            way_id = int(way_id)
            # change the format of coordinates for an easier use
            coordinates = get_nice_coordinates(coordinates)

            nodes = []
            for coord in coordinates:
                # we build a function to get the nearest node to a points in a digraph
                # otherwise it would be way too slow
                nodes.append(my_nearest_node(graph, coord[0], coord[1]))

            edges = []
            for i in range(len(nodes)-1):
                try:
                    path = osmnx.shortest_path(graph, nodes[i], nodes[i+1])
                except Exception as e:
                    continue

                if path is not None:
                    for j in range(len(path)-1):
                        edges.append((path[j], path[j+1]))

            while(len(highways) <= way_id):
                highways.append(Highway(0, 0, 0))

            # the position of each highway in the vector is its id (to locate its congestion later)
            highways[way_id] = Highway(description, edges, coordinates)

        return highways


def my_nearest_node(graph, x, y):
    '''
    Auxiliar method of download_and_build_highways
    Returns the closest node of a graph to a point
    Arguments:
        graph -> graph of the streets
        x, y -> coordinates of the point
    Complexity:
        O(n) where n is the number of nodes in the graph
    '''

    best_node = None
    best_dist = 1e10
    for node, info in graph.nodes.items():
        this_dist = (x-info['x'])**2 + (y-info['y'])**2
        if this_dist < best_dist:
            best_dist = this_dist
            best_node = node
    return best_node


def get_nice_coordinates(coordinates):
    '''
    Auxiliar method of download_and_build_highways
    Returns a vector of the coordinates in the desired format
    Arguments:
        coordinates -> string with the coordinates (string)
    Complexity:
        O(n) where n is the number of coordinates
    '''

    # get a vector with all the coordinates
    coordinates = coordinates.split(',')
    for i in range(len(coordinates)):
        coordinates[i] = float(coordinates[i])

    # group each pair of coordinates in a tuple
    grouped_coordinates = []
    for i in range(0, len(coordinates), 2):
        grouped_coordinates.append((coordinates[i], coordinates[i+1]))

    return grouped_coordinates


def download_congestions(CONGESTIONS_URL):
    '''
    Returns the congestions of a city from the web
    Arguments:
        CONGESTIONS_URL -> url where the congestions are (string, link)
    Complexity:
        O(n) where n is the number of congestions
    '''

    with urllib.request.urlopen(CONGESTIONS_URL) as response:
        # put all the lines of the webpage in a vector
        lines = [line.decode('utf-8') for line in response.readlines()]

        # read them and store them in a vector
        reader = csv.reader(lines, delimiter='#')

        congestions = []
        for line in reader:
            way_id, date, current, predicted = line
            way_id = int(way_id)
            current = int(current)
            predicted = int(predicted)
            congestions.append(Congestion(way_id, current, predicted))

        return congestions


def plot_congestions(highways, congestions, CONGESTIONS_FILENAME, SIZE):
    '''
    Get a map with the congestions plotted
    Arguments:
        highways -> streets whose congestions we know (vector of highway)
        congestions -> congestions of those streets (vector of congestions)
        CONGESTIONS_FILENAME -> filename where the map has to be stored (string ended in ".png")
        SIZE -> size of the map (int)
    Complexity:
        O(n) where n is the number of congestions
    '''

    # each type of congestion has a different color to be plotted with
    congestion_colors = ["gray", "green", "palegreen", "yellow", "orange", "red", "black"]
    m = StaticMap(SIZE, SIZE)
    for c in congestions:
        for i in range(len(highways[c.way_id].coordinates)-1):
            coord1 = highways[c.way_id].coordinates[i]
            coord2 = highways[c.way_id].coordinates[i+1]
            m.add_line(Line((coord1, coord2), congestion_colors[c.current], 2))
    m.render().save(CONGESTIONS_FILENAME)


def build_igraph(graph, highways, congestions, context=None, chat_id=None, message_id=None):
    '''
    Returns the igraph (graph with itime in edges)
    (optional) It also tells the Telegram user the % that has already been loaded, changing the last message the bot sent
    Arguments:
        graph -> graph of the streets
        highways -> streets whose congestions we know (vector of highway)
        congestions -> congestions of those streets (vector of congestions)
        Optionals:
        context -> context of the telegram bot
        chat_id -> id of the chat with the user (int)
        message_id -> id of the last message of our bot (int)
    Complexity:
        O(m + n*c) where
            m is the number of edges in the graph
            n is the number of nodes in the graph
            c is the number of congestions
    '''

    # first we add maxspeed, time and congestion (with an initial value of 0) to all edges
    graph = force_maxspeed(graph)
    graph = add_time_and_0congestion(graph)

    curr = 0
    # and for each congestion we change the congestion value of its respective edges
    for i in range(len(congestions)):

        # if the option is active, show the percentage
        if context is not None:
            next = 7*(100*i//(len(congestions)*7))
            if curr != next:
                curr = next
                context.bot.editMessageText(chat_id=chat_id,
                                            message_id=message_id,
                                            text=str(curr) + "%")

        c = congestions[i]
        for edge in highways[c.way_id].edges:
            graph.edges[edge]['congestion'] = c.current

    if context is not None:
        context.bot.editMessageText(chat_id=chat_id,
                                    message_id=message_id,
                                    text="100%, graph updated")

    # finally we add the itime to the edges
    graph = add_itime(graph)
    return graph


def force_maxspeed(graph):
    '''
    Auxiliar method of build_igraph
    Returns the graph with all edges with maxspeed
    Arguments:
        graph -> graph of the streets
    Complexity:
        O(m) where m is the number of edges in the graph
    '''

    for e in graph.edges.items():
        if 'maxspeed' not in e[1]:

            # if highway of the edge is a list, take the most relevant element
            if isinstance(e[1]['highway'], list):
                if 'residential' in e[1]['highway']:
                    e[1]['highway'] = 'residential'
                elif 'secondary' in e[1]['highway'] or 'primary' in e[1]['highway'] or 'primary_link' in e[1]['highway']:
                    e[1]['highway'] = 'primary'
                elif 'residential' in e[1]['highway'] or 'tertiary' in e[1]['highway']:
                    e[1]['highway'] = 'residential'
                elif 'living_street' in e[1]['highway']:
                    e[1]['highway'] = 'living_street'
                elif 'unclassified' in e[1]['highway']:
                    e[1]['highway'] = 'unclassified'

            # set a maxspeed for the edge depending on the type of road ("highway") it is
            if e[1]['highway'] == 'trunk_link':
                e[1]['maxspeed'] = '60'
            elif e[1]['highway'] == 'secondary' or e[1]['highway'] == 'primary' or e[1]['highway'] == 'primary_link':
                e[1]['maxspeed'] = '50'
            elif e[1]['highway'] == 'residential' or e[1]['highway'] == 'tertiary':
                e[1]['maxspeed'] = '30'
            elif e[1]['highway'] == 'living_street':
                e[1]['maxspeed'] = '20'
            elif e[1]['highway'] == 'unclassified':
                e[1]['maxspeed'] = '10'

    return graph


def add_time_and_0congestion(graph):
    '''
    Auxiliar method of build_igraph
    Returns the graph with all edges with congestion = 0 and time (with no congestion)
    Arguments:
        graph -> graph with all edges with maxspeed
    Complexity:
        O(m) where m is the number of edges in the graph
    '''

    for e in graph.edges.items():
        if isinstance(e[1]['maxspeed'], list):
            e[1]['maxspeed'] = max(e[1]['maxspeed'])
        e[1]['time'] = e[1]['length'] / float(e[1]['maxspeed'])
        e[1]['congestion'] = 0
    return graph


def add_itime(graph):
    '''
    Auxiliar method of build_igraph
    Returns the graph with all edges with itime
    Arguments:
        graph -> graph with all edges with time and congestion
    Complexity:
        O(m) where m is the number of edges in the graph
    '''

    # each congestion type multiplies the time a given amount
    multipliers = [1.1, 1, 1.2, 1.5, 2, 4, 1e12]
    for e in graph.edges.items():
        e[1]['itime'] = e[1]['time'] * multipliers[e[1]['congestion']]

    return graph


def do_path(igraph, begin, end, PATH_FILENAME, SIZE):
    '''
    Get a map with the fastest path from one point to another plotted
    Arguments:
        igraph -> igraph of the streets of the city
        begin -> origin of the trajectory (string eith geocode or tuple with coordinates)
        end -> destination of the trajectory (string eith geocode or tuple with coordinates)
        PATH_FILENAME -> filename where the map has to be stored (string ended in ".png")
        SIZE -> size of the map
    Complexity:
        same as osmnx.shortest_path
    '''

    path = get_shortest_path_with_ispeeds(igraph, begin, end)
    plot_path(igraph, path, PATH_FILENAME, SIZE)


def get_shortest_path_with_ispeeds(igraph, begin, end):
    '''
    Auxiliar method of do_path
    Returns the nodes of the fastest path
    Arguments:
        igraph -> igraph of the streets of the city
        begin -> origin of the trajectory (string eith geocode or tuple with coordinates)
        end -> destination of the trajectory (string eith geocode or tuple with coordinates)
    Complexity:
        same as osmnx.shortest_path
    '''

    # converts begin and end into its respective nodes
    if type(begin) == str:
        begin = osmnx.geocode(begin + ", Barcelona")
    if type(end) == str:
        end = osmnx.geocode(end + ", Barcelona")
    begin = my_nearest_node(igraph, begin[1], begin[0])
    end = my_nearest_node(igraph, end[1], end[0])
    # we reuse the function we have already built

    # and returns its shortest_path
    return osmnx.shortest_path(igraph, begin, end, weight='itime')


def plot_path(igraph, path, PATH_FILENAME, SIZE):
    '''
    Auxiliar method of do_path
    Plots the path in the map and saves it
    Arguments:
        igraph -> igraph of the streets of the city
        path -> nodes of the fastest path
        PATH_FILENAME -> filename where the map has to be stored (string ended in ".png")
        SIZE -> size of the map
    Complexity:
        O(n) where n is the number of nodes on the path
    '''

    # if the congestion is high, we mark it in the corresponding color
    congestion_colors = ["blue", "blue", "blue", "yellow", "orange", "red", "black"]
    m = StaticMap(SIZE, SIZE)
    for i in range(len(path)-1):
        # plot each edge into the map with a color representing its congestion
        node1 = igraph.nodes[path[i]]
        node2 = igraph.nodes[path[i+1]]
        color = congestion_colors[igraph.edges[(path[i], path[i+1])]['congestion']]
        m.add_line(Line(((node1['x'], node1['y']), (node2['x'], node2['y'])), color, 5))

    m.render().save(PATH_FILENAME)
