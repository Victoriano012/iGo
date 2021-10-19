from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from igo import *

PLACE = 'Barcelona, Catalonia'
GRAPH_FILENAME = 'barcelona.graph'
SIZE = 800
HIGHWAYS_URL = 'https://opendata-ajuntament.barcelona.cat/data/dataset/1090983a-1c40-4609-8620-14ad49aae3ab/resource/1d6c814c-70ef-4147-aa16-a49ddb952f72/download/transit_relacio_trams.csv'
CONGESTIONS_URL = 'https://opendata-ajuntament.barcelona.cat/data/dataset/8319c2b1-4c21-4962-9acd-6db4c5ff1148/resource/2d456eb5-4ea6-4f68-9794-2f3f1a58a933/download'

graph = get_graph(GRAPH_FILENAME, PLACE)
highways = download_and_build_highways(HIGHWAYS_URL, graph)

start_text = "Hi, I'm iGoBot! \nThe bot that will change your live. \nIn order to be usefull I will need your location. If you dont know how to use me, write the /help command"
help_text = "You can control me by sending this commands: \n \n /author: show the name of the project authors. \n /go: show a map with the path to arrive to your destination. \n /where: show a map whith your location. \n /congestions: show a map with the congestions. "
author_text = "The project authors are Víctor Conchello and Gerard Comas."


def start(update, context):
    '''
    Start a conversation with iGoBot. Beware whith this function,
    because it restarts the location.
    Complexity:
        O(1)
    '''
    # If it is the first time that the /start command is used since the
    # last execution of the bot, the 'congestions' attribute will not exist.
    if 'congestions' not in context.bot_data:
        context.bot_data['congestions'] = False
    # If it is the first time that the /start command is used since the last
    # execution of the bot, the 'igraph' attribute will not exist.
    if 'igraph' not in context.bot_data:
        context.bot_data['igraph'] = False
    # When the /start command is used, it restarts the location.
    context.user_data['location'] = None
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=start_text)


def help(update, context):
    '''
    Show the command list and a brief explanation of each command.
    Complexity:
        O(1)
    '''
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=help_text)


def author(update, context):
    '''
    Show the name of the project authors.
    Complexity:
        O(1)
    '''
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text=author_text)


def go(update, context):
    '''
    Show a map with the path to arrive to your destination.
    You must write a destination.
    Complexity:
        same as do_path, except when congestions have to be updated,
        in that case same as build_igraph.
    '''
    message = update.message.text[4:]
    if len(message) == 0:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="You must write a destination.")
        return
    update_congestions(update, context)
    destination = read_pos(message)
    if context.user_data['location'] is not None:
        origin = context.user_data['location']
    else:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="I don't know your location, please it to me.")
        return
    file = "path.png"
    try:
        do_path(context.bot_data['igraph'], origin, destination, file, SIZE)
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="You have to follow this path:")
        context.bot.send_photo(chat_id=update.effective_chat.id,
                               photo=open(file, 'rb'))
        # Remove the file to free up memory space
        os.remove(file)
    except Exception as e:
        print(e)
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="There is no path between your location and your destination.")


def where(update, context):
    '''
    Show a map whith your location.
    Complexity:
        same as StaticMap functions
    '''
    if context.user_data['location'] is None:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="I don't know your location, please send it to me.")
        return
    else:
        lat, lon = context.user_data['location']
    file = "where.png"
    map = StaticMap(SIZE, SIZE)
    map.add_marker(CircleMarker((lon, lat), 'blue', 15))
    map.render().save(file)
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text="You are here:")
    context.bot.send_photo(chat_id=update.effective_chat.id,
                           photo=open(file, 'rb'))
    os.remove(file)


def congestions(update, context):
    '''
    Plot the congestions.
    Complexity:
        same as plot_congetions, except when congestions have to be updated,
        in that case same as build_igraph.
    '''
    update_congestions(update, context)
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text="Here you have the congestions:")
    plot_congestions(highways, context.bot_data['congestions'],
                     "congestions.png", SIZE)
    context.bot.send_photo(chat_id=update.effective_chat.id,
                           photo=open("congestions.png", 'rb'))


def pos(update, context):
    '''
    Change the location of the user You must write a location.
    Complexity:
        O(1)
    '''
    message = update.message.text[5:]
    if len(message) == 0:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="You must write a location.")
        return
    context.user_data['location'] = read_pos(message)
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text="Location change completed successfully.")


def read_pos(position):
    '''
    Read a position and return the position with the appropiate format.
    Complexity:
        O(1)
    '''
    separate = position.split(' ')
    try:
        return (float(separate[0]), float(separate[1]))
    except Exception as e:
        return osmnx.geocode(position + ", Barcelona")


def get_loc(update, context):
    '''
    Get the location of the user.
    Complexity:
        O(1)
    '''
    context.user_data['location'] = (update.message.location.latitude,
                                     update.message.location.longitude)
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text="Received.")


def update_congestions(update, context):
    '''
    Load the congestions if they are not updated.
    Complexity:
        same as build_igraph
    '''
    new_congestions = download_congestions(CONGESTIONS_URL)
    # The congestion changes every 15 minutes, if there is a change the
    # congestions will have to be reloaded
    if new_congestions != context.bot_data['congestions']:
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="I have to update the map, wait a few seconds.")
        context.bot_data['congestions'] = new_congestions
        message = context.bot.send_message(chat_id=update.effective_chat.id,
                                           text="0%")
        # It will reload also the igraf to avoid problems with versions
        context.bot_data['igraph'] = build_igraph(graph, highways, context.bot_data['congestions'],
                                                  context,  update.effective_chat.id, message.message_id)


# Declare a constant amb the access token that got from token.txt
TOKEN = open('token.txt').read().strip()

# Creates objects to work with Telegram
updater = Updater(token=TOKEN, use_context=True)
dispatcher = updater.dispatcher

# Indicates that when the bot receives the /*command*,
# the *command* function is executed
dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(CommandHandler('help', help))
dispatcher.add_handler(CommandHandler('author', author))
dispatcher.add_handler(CommandHandler('go', go))
dispatcher.add_handler(CommandHandler('where', where))
dispatcher.add_handler(CommandHandler('pos', pos))
dispatcher.add_handler(CommandHandler('congestions', congestions))

# When the bot receives a location, the get_loc function is executed
dispatcher.add_handler(MessageHandler(Filters.location, get_loc))

# Start the bot
updater.start_polling()

print("all done")
