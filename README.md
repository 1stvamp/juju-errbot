# juju-errbot
A [reactive](https://pythonhosted.org/charms.reactive/) [Juju charm](http://jujucharms.com/) layer used to build the errbot charm, which in turn can be used to deploy the [errbot](http://errbot.io/) chat bot.

## Getting started

```sh
sudo add-apt-repository ppa:juju/stable
sudo apt update
sudo apt install charm-tools
mkdir -p ~/charms/layers
cd !$
git clone https://github.com/1stvamp/juju-errbot.git
cd juju-errbot
charm build
```
