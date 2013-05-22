anybodymagic
============

Extension for IPython to run AnyBody macros

### Install
`%install_ext https://raw.github.com/melund/anybodymagic/master/anybodymagic.py`

### Usage

`%load_ext anybodymagic`

``` 
%%anybody 
load "MyModel.main.any"
operation Main.MyStudy.InverseDynamics
run
classoperation Main.MyStudy.Output "Save data" --type="Deep" --file="output.anydata.h5"
exit
```

For more details see this [demo of anybodymagic](http://nbviewer.ipython.org/urls/raw.github.com/melund/anybodymagic/master/demo_anybodymagic.ipynb)
