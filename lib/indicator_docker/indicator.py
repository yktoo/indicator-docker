import logging
import docker

from gi import require_version
from gi.repository import GObject

require_version('Notify', '0.7')
from gi.repository import Notify

require_version('Gtk', '3.0')
from gi.repository import Gtk

require_version('AppIndicator3', '0.1')
from gi.repository import AppIndicator3 as AppIndicator

from indicator_docker.event_thread import EventThread

# Global definitions
APP_ID      = 'indicator-docker'
APP_NAME    = 'Docker Indicator'
APP_ICON    = 'indicator-docker'
APP_VERSION = '0.1.0'
APP_LICENCE = """This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License version 3, as published
by the Free Software Foundation.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranties of
MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program. If not, see http://www.gnu.org/licenses/"""


class DockerIndicator(GObject.GObject):

    STATUSES_IN_SCOPE = ['create', 'start', 'stop', 'die', 'destroy']

    def __init__(self):
        """Constructor."""
        GObject.GObject.__init__(self)

        self.item_separator = None
        self.num_containers = 0
        self.notification = None

        # Create the indicator object
        self.ind = AppIndicator.Indicator.new(APP_ID, APP_ICON, AppIndicator.IndicatorCategory.HARDWARE)
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)

        # Create a menu
        self.menu = Gtk.Menu()
        self.ind.set_menu(self.menu)
        self.menu_setup()

        # Init notifications
        Notify.init(APP_ID)

        # Connect to the Docker daemon
        self.docker_client = docker.from_env()
        logging.info('Connected to Docker daemon')
        for k, v in self.docker_client.info().items():
            logging.info('    %s: %s', k, str(v))

        # Update the items
        self.update_list()

        # Start the event handler thread
        self.event_thread = EventThread(self.docker_client, self.event_callback)
        self.event_thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def on_about(*args):
        """Signal handler: About item clicked."""
        logging.debug('.on_about()')
        dialog = Gtk.AboutDialog()
        dialog.set_program_name(APP_NAME)
        dialog.set_copyright(_('Written by Dmitry Kann'))
        dialog.set_license(APP_LICENCE)
        dialog.set_version(APP_VERSION)
        dialog.set_website('http://yktoo.com')
        dialog.set_website_label('yktoo.com')
        dialog.set_logo_icon_name(APP_ICON)
        dialog.connect('response', lambda x, y: dialog.destroy())
        dialog.run()

    def on_quit(self, *args):
        """Signal handler: Quit item clicked."""
        logging.debug('.on_quit()')
        self.shutdown()

    def on_refresh(self, *args):
        """Signal handler: Refresh item clicked."""
        logging.debug('.on_refresh()')
        self.update_list()

    def on_stop_all(self, *args):
        """Signal handler: Stop All item clicked."""
        logging.debug('.on_stop_all()')
        for container in self.docker_client.containers.list():
            container.stop()

    @staticmethod
    def on_container_select(widget, container):
        """Signal handler: container item clicked."""
        logging.debug('.on_container_select(), container name: `%s`', container.name)
        if container.status == 'running':
            logging.info('Stopping container `%s`', container.name)
            container.stop()
        else:
            logging.info('Starting container `%s`', container.name)
            container.start()

    def event_callback(self, event):
        """Event handler callback. Is called in the context of the event handler thread."""
        # Check the event's status and type
        if 'status' not in event or 'Type' not in event or event['Type'] != 'container':
            return

        # If the status is of interest
        if event['status'] in self.STATUSES_IN_SCOPE:
            # Pass the event on to the main GUI thread
            GObject.idle_add(self.handle_docker_event, event)

    def handle_docker_event(self, event):
        """Event handler. Is called in the context of the main GUI thread."""
        # Send a desktop notification
        if event['status'] == 'start':
            self.notify(_('Container "{}" has been started').format(event['Actor']['Attributes']['name']))
        elif event['status'] == 'stop':
            self.notify(_('Container "{}" has been stopped').format(event['Actor']['Attributes']['name']))

        # Update the container menu
        self.update_list()

    # ------------------------------------------------------------------------------------------------------------------
    # Other methods
    # ------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def run():
        """Run the application."""
        # Run the main event loop
        Gtk.main()

    def notify(self, text: str):
        """Send a notification message to the desktop."""
        # Remove any existing notification
        if self.notification is None:
            self.notification = Notify.Notification.new(APP_NAME, text, APP_ICON)
        else:
            self.notification.update(APP_NAME, text, APP_ICON)
        self.notification.show()

    def menu_append_item(self, label: str=None, activate_signal: callable=None):
        """Add an item (if label is None then a separator item) to the indicator menu.
         :return: the created item"""
        if label is None:
            item = Gtk.SeparatorMenuItem()
        else:
            item = Gtk.MenuItem.new_with_mnemonic(label)
            if activate_signal is not None:
                item.connect('activate', activate_signal, None)
            else:
                item.set_sensitive(False)
        item.show()
        self.menu.append(item)
        return item

    def menu_insert_ordered_item(self, after_item, before_item, label: str, show: bool):
        """Insert a new menu item into the menu between after_item and before_item, maintaining alphabetical order of
        the items.
        :return: the created item
        """
        # Find out item indexes
        items = self.menu.get_children()
        idx_from = 0 if after_item is None else items.index(after_item) + 1
        idx_to   = items.index(before_item)

        # Create and setup a new check item
        new_item = Gtk.CheckMenuItem.new_with_label(label)
        if show:
            new_item.show()

        # Find an appropriate position for the item so that they are in alphabetical order
        i = idx_from
        while (i < idx_to) and (label >= items[i].get_label()):
            i += 1

        # Insert the item
        self.menu.insert(new_item, i)
        return new_item

    def menu_setup(self):
        """Initialise the indicator menu."""
        # Add static items
        self.item_separator = self.menu_append_item()
        self.menu_append_item(_('_Stop all'), self.on_stop_all)
        self.menu_append_item(_('_Refresh'), self.on_refresh)
        self.menu_append_item(_('_About'), self.on_about)
        self.menu_append_item(_('_Quit'), self.on_quit)

    def update_list(self):
        """Update the list of containers."""
        # Clean up the menu
        items = self.menu.get_children()
        for i in range(0, self.num_containers):
            self.menu.remove(items[i])

        # Load container list
        self.num_containers = 0
        for container in self.docker_client.containers.list(all=True):
            item = self.menu_insert_ordered_item(None, self.item_separator, container.name, True)
            # Set checkmark if the container's active
            item.set_active(container.status == 'running')
            # Connect click signal after that
            item.connect('activate', self.on_container_select, container)
            self.num_containers += 1

    def shutdown(self):
        """Shut down the application."""
        logging.info('Shutting down...')
        # Shut down the event handler thread (and give it a sec to clean up)
        self.event_thread.terminated = True
        self.event_thread.join(1.0)

        # Clean up notifications
        Notify.uninit()

        # Quit the app
        Gtk.main_quit()
