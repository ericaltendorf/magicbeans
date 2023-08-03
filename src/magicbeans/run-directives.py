from magicbeans import config

if __name__ == '__main__':
   network = config.get_network()
   print()
   print(network.generate_account_directives("2000-01-01"))  
   print()