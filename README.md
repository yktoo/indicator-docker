Docker Indicator
================

A very basic implementation of application indicator for controlling [Docker](https://www.docker.com/) containers.


Available functionality
-----------------------

* Displaying a live list of available containers (both running and stopped). The list is updated automatically thanks to Docker daemon event subscription.
* Starting and stopping a container by selecting the corresponding menu item.
* Displaying a desktop notification whenever a container is started or stopped (not necessarily via the indicator).


Requirements
------------

* Python 3
* gir1.2-appindicator3-0.1
* gettext
* docker (`sudo pip install docker`)
