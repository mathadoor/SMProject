import base64
import streamlit as st
from st_click_detector import click_detector
from PIL import Image
import numpy as np
from translator import inference
import matplotlib.pyplot as plt

st.set_page_config(page_title='Img2LATeX', page_icon=':pencil2:')


# The following functions are copied from https://github.com/vivien000/st-click-detector/issues/4 to display local
# images
def initialize_state():
    '''
    Initialize the state of the app
    :return:
    '''
    st.session_state['initialized'] = True
    st.session_state['selected_image'] = None
    st.session_state['np_image'] = None
    st.session_state['label'] = None
    st.session_state['alphas'] = None
    st.session_state['active_alpha'] = None
    st.session_state['type_input'] = 'From a Pre-Existing Set'


def clean_label(_label):
    """
    Clean the label to be displayed. If the label is a + or -, then it is escaped so that it is not interpreted as a
    command
    :param _label: The label to be cleaned
    :return: The cleaned label
    """
    if _label == '+':
        return r'\+'
    elif _label == '-':
        return r'\-'
    return _label


def base64img(path: str):
    """
    Convert an image to base64
    :param path: The path to the image
    """
    with open(path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('utf-8')
        return data


def images_html(examples):
    """
    Create the html for the images
    :param examples: array of paths to the images
    :return: The html markup for the images insertion
    """
    contents = [
        f"<a href='#' id='{i}'><img width='180' alt='{examples[i]}' src='data:image/png;base64,{base64img(path)}'></a>"
        for i, path in enumerate(examples)]
    return f'{"&nbsp;" * 2}'.join(contents)


def active_alpha(_index):
    """
    Set the active alpha to the index of the token clicked to show the attention map
    :param _index: The index of the token clicked
    """
    st.session_state['active_alpha'] = _index


# Intialize the needed state variables and the image arrays

if 'initialized' not in st.session_state:
    initialize_state()

image_arrays = [
    "data/CROHME/train/off_image_train/73_herbert_0.bmp",
    "data/CROHME/train/off_image_train/93_alfonso_0.bmp",
    "data/CROHME/train/off_image_train/94_bruno_0.bmp",
]

st.title('Handwritten Equations to Latex Translator')

st.write('### Introduction:')
st.write('''This page serves to demonstrate a machine learning based object character recognition system. The underlying model was trained on the 
[CROHME](https://researchdata.edu.au/crohme-competition-recognition-expressions-png/639782) dataset. It implements
the watch-attend-parse architecture from [this paper](https://www.sciencedirect.com/science/article/pii/S0031320317302376). 
The details of the project can be found in its [repository](https://github.com/mathadoor/ImageToLatex). 

The application on this page offers interaction with the inference harness of the system. The interface provides two methods to select an image to translate.
The first allows the selection from a pre-existing set of images. The second allows the user to upload an image. The user can then
click on the translate button to decode the image into the corresponding LaTeX encodings. Subsequently, a toggle option is presented to enable the attention maps. Using these maps, 
the user can visualize the image patches the model is attending to while decoding a certain token. 

Note: The model is trained under limited compute and data. As such, it may not give reasonable performance on out-of-distribution samples and all possible symbols of LaTeX.''')

# Define the input image options
st.write('### Input image:')
st.session_state['type_input'] = st.selectbox('How would you like to input the image?',
                                              ('From a Pre-Existing Set', 'Upload Image'))

if st.session_state['type_input'] == 'Upload Image':
    st.session_state['selected_image'] = st.file_uploader('Upload an image', type=['png', 'jpg', 'jpeg', 'bmp'])
else:
    select_image = click_detector(images_html(image_arrays))
    if select_image == "":
        select_image = "0"
    st.session_state['selected_image'] = image_arrays[int(select_image)]

if st.session_state['selected_image'] is not None:
    st.write('### Selected Image:')
    image = Image.open(st.session_state['selected_image'])
    numpy_array = np.array(image) / 255.0
    # Plot the numpy image to matplotlib figure in grayscale
    fig, ax = plt.subplots()
    ax.imshow(numpy_array)

    if st.session_state['active_alpha'] is not None:
        index = st.session_state['active_alpha']
        expected_shape = list(numpy_array.shape)
        attention = inference.pass_attention(st.session_state['alphas'][index], expected_shape)
        st.session_state['active_alpha'] = None
        ax.imshow(attention, cmap='gray', alpha=0.4, extent=(0, expected_shape[1], expected_shape[0], 0))

    ax.axis('off')
    st.pyplot(fig)

# Define the translating options
clicked = st.button('Translate Text')

if clicked and st.session_state['selected_image'] is not None:
    model = inference.load_model()
    label, alphas = inference.translate(model, st.session_state['selected_image'])
    st.session_state['label'] = label
    st.session_state['alphas'] = alphas

# Define the token display options
attention_show = st.toggle('Show Attention Map', value=False)
if st.session_state['label'] is not None and st.session_state['selected_image'] is not None:
    st.write('### Translated Latex:')
    if not attention_show:
        st.markdown("**Encoding**: " + st.session_state['label'])
        st.markdown("**Rendered Equation**: $" + st.session_state['label'] + "$")
    else:
        st.caption('Click on a token to see the attention map i.e what corresponding image patches are being attended '
                   'to')
        # Show the tokens as buttons. The buttons are arranged in columns such that the length of each button is
        # proportional to the length of the token, and they are arranged with uniform gap.
        label_show = st.session_state['label'].split(' ')
        max_val = 100
        a, b = 0.98, 6
        num_labels = len(label_show)
        curr_l = 0
        columns_array = []
        start = 0
        for i in range(num_labels):
            l = label_show[i]
            new_l = a * len(l) + b
            if curr_l + new_l <= max_val and i != num_labels - 1:
                columns_array += [new_l]
                curr_l += new_l
            elif len(columns_array) != 0:
                if i == num_labels - 1:
                    i = i + 1
                    columns_array += [new_l]
                    curr_l += new_l
                columns_array = columns_array if curr_l == max_val else columns_array + [max_val - curr_l]
                columns = st.columns(columns_array)
                for j in range(start, i):
                    with columns[j - start]:
                        st.button(clean_label(label_show[j]), key=j, on_click=active_alpha, kwargs={'_index': j},
                                  use_container_width=True)
                start = i
                if curr_l + new_l > max_val:
                    columns_array = [new_l]
                    curr_l = new_l
                else:
                    columns_array = []
                    curr_l = 0

        st.button('Reset Attention', key=-1, on_click=active_alpha, kwargs={'_index': None}, use_container_width=True)
