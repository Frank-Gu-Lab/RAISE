# Contact Angle Analyzer
from skimage import color, draw, io, feature, filters, exposure, morphology, measure, transform
from multiprocessing import Event
from multiprocessing.connection import Connection
from typing import List, Tuple
from datetime import datetime
from preprocessing import extract_edges_CV, prepare_hydrophobic
from BA_fit import YL_fit
import matplotlib.pyplot as plt
import matplotlib
import numpy as np
import math

matplotlib.use('agg')

def raise_precheck(img: np.ndarray) -> bool:
    img_shape: Tuple[int, int] = img.shape
    
    img_gray: np.ndarray | None = None
    if len(img_shape) == 3:
        img_gray = color.rgb2gray(img)
    else:
        img_gray = img
    
    # Find search area
    img_blur = filters.gaussian(img_gray, sigma=1)
    thr = filters.threshold_otsu(img_blur)
    img_thr = img_blur > thr

    labels = measure.label(img_thr)
    props_tbl = measure.regionprops_table(labels, properties=('label', 'bbox', 'area'))
    idx_max = props_tbl['area'].argmax()
    min_row, min_col, max_row, max_col = props_tbl['bbox-0'][idx_max], \
                                         props_tbl['bbox-1'][idx_max], \
                                         props_tbl['bbox-2'][idx_max], \
                                         props_tbl['bbox-3'][idx_max]
    
    if (min_col != 0) or (max_col != img_gray.shape[1]):
        background_width = max_col - min_col
        trim = background_width // 10
        min_col += trim
        max_col -= trim
    background_crop_width = max_col - min_col
    background_crop_height = max_row - min_row
    #print(min_row, min_col, max_row, max_col)

    max_dimension = max(background_crop_width, background_crop_height)

    img_crop = img_gray[min_row:max_row , min_col:max_col]

    # Find droplet
    edges = feature.canny(img_crop, sigma=5)
    hough_radii = np.arange(50, max_dimension, 5)
    hough_res = transform.hough_circle(edges, hough_radii)
    _, cx, cy, rad = transform.hough_circle_peaks(hough_res, hough_radii, num_peaks=1, total_num_peaks=5)

    #print(len(rad))
    if len(rad) == 0:
        return False
    
    #fig, ax = plt.subplots(figsize=(10, 6))
    #rr, cc = draw.circle_perimeter(cy[0], cx[0], rad[0], shape=img_crop.shape)
    #img_crop = color.gray2rgb(img_crop)
    #img_crop[rr, cc] = (255, 0, 0)
    #ax.imshow(img_crop, cmap='Greys_r')
    #plt.show()

    return True


def crop_image(img: np.ndarray):
    assert len(img.shape) == 2
    img_height, img_width = img.shape

    # Sobel filter
    edges = filters.sobel(img)

    # grayscale white-tophat operation with small structure element
    se = morphology.footprint_rectangle((5, 5))
    img_gs_morph = morphology.white_tophat(edges, footprint=se)

    # Rescale white-tophat to [0, 255]
    img_gs_morph = (img_gs_morph - np.min(img_gs_morph)) / np.max(img_gs_morph) * 255

    # Binarize image
    thr = filters.threshold_otsu(img_gs_morph)
    img_thr = img_gs_morph > thr

    # Get bounding box of edge image
    labels = measure.label(img_thr)
    props_tbl = measure.regionprops_table(labels, properties=('area_bbox', 'bbox'))
    argmax = np.argmax(props_tbl['area_bbox'])
    min_row, min_col = props_tbl['bbox-0'][argmax], props_tbl['bbox-1'][argmax]
    max_row, max_col = props_tbl['bbox-2'][argmax], props_tbl['bbox-3'][argmax]

    # Add ~25% padding to the bounding box
    row_c, col_c = (max_row + min_row) // 2, (max_col + min_col) // 2
    max_dim = max(max_row - min_row, max_col - min_col)
    min_row = max(0, row_c - max_dim * 5 // 8)
    max_row = min(row_c + max_dim * 5 // 8, img_height)
    min_col = max(0, col_c - max_dim * 5 // 8)
    max_col = min(col_c + max_dim * 5 // 8, img_width)

    #fig, ax = plt.subplots(figsize=(10, 6))
    #img_rgb = color.gray2rgb(img)
    #rr, cc = draw.rectangle_perimeter((min_row, min_col), (max_row, max_col), shape=img.shape)
    #img_rgb[rr, cc] = (255, 0, 0)
    #ax.imshow(img_rgb, cmap='Greys_r')
    #plt.show()
    #plt.close()

    return img[min_row:max_row, min_col:max_col]

def set_baseline(img: np.ndarray):
    assert len(img.shape) == 2
    img_height, img_width = img.shape
    img_blur = filters.gaussian(img, sigma=1)
    img_blur = exposure.rescale_intensity(img_blur, out_range='uint8')
    #print(img_blur.shape, img_blur.dtype)

    img_gamma_corr = exposure.adjust_gamma(img_blur, gamma=0.3)

    #fig, ax = plt.subplots(figsize=(10, 6))
    #ax.imshow(img_gamma_corr, cmap='Greys_r')
    #plt.show()
    #plt.close()

    edges = filters.sobel(img_blur)
    edges = (edges - np.min(edges)) / np.max(edges) * 255

    # Binarize image
    thr = filters.threshold_otsu(img_gamma_corr)
    img_thr = img_gamma_corr > thr

    # Binarize edge image
    thr_edges = filters.threshold_otsu(edges)
    img_thr_edges = edges > thr_edges

    labels = measure.label(img_thr)
    props_tbl = measure.regionprops_table(labels, properties=('label', 'area_bbox'))
    argmax = np.argmax(props_tbl['area_bbox'])
    main_label = props_tbl['label'][argmax]

    img_drop = labels == main_label
    #img_drop = morphology.binary_dilation(img_drop)

    mid_col = img_width // 2
    img_drop_left = img_thr_edges[:, :mid_col]
    img_drop_right = img_thr_edges[:, mid_col:]

    max_rows = []
    for img_half in [img_drop_left, img_drop_right]:
        labels = measure.label(img_half)
        props_tbl = measure.regionprops_table(labels, properties=('label', 'area_bbox', 'bbox'))
        argmax = np.argmax(props_tbl['area_bbox'])
        max_rows.append(props_tbl['bbox-2'][argmax])
    
    #print(max_rows)
    baseline_row = min(max_rows) - 10
    img_drop[baseline_row:, :] = False

    img_processed = np.zeros(img_drop.shape, dtype='uint8')
    img_processed[img_drop] = 255

    #fig, ax = plt.subplots(figsize=(10, 6))
    #ax.imshow(img_processed, cmap='Greys_r')
    #plt.show()
    #plt.close()

    return img_processed, baseline_row

def get_main_contour(img: np.ndarray):
    assert len(img.shape) == 2
    img_height, img_width = img.shape

    contours = measure.find_contours(img, level=0)
    argmax = np.argmax([len(contour) for contour in contours])

    main_contour = contours[argmax]
    if main_contour[0, 1] > main_contour[-1, 1]:
        main_contour = main_contour[::-1, :]

    #fig, ax = plt.subplots(figsize=(10, 6))
    #ax.imshow(img, cmap='Greys_r')
    #ax.plot((main_contour.T)[1], (main_contour.T)[0])
    #plt.show()
    #plt.close()

    return main_contour

def find_inflection_point(contour: np.ndarray):
    y, x = contour.T
    gradients = np.gradient(x, np.arange(len(x)))
    assert len(x) == len(gradients)

    signs = np.zeros(gradients.shape)
    mask = gradients > 0
    signs[mask] = 1

    delta_signs = np.diff(signs, prepend=signs[0])
    #print(delta_signs)
    delta_signs = np.abs(delta_signs)
    assert len(delta_signs) == len(x)

    num_inflections = np.sum(delta_signs)
    argwhere = np.nonzero(delta_signs)
    #print(argwhere)
    idx_inflection = -1
    if num_inflections > 1:
        idx_inflection = argwhere[0][1]
    else:
        idx_inflection = argwhere[0][0]

    #fig, ax = plt.subplots(figsize=(10, 6))
    #ax.plot(gradients)
    #ax.plot(delta_signs)
    #plt.show()
    #plt.close()

    #print(idx_inflection)
    return int(idx_inflection), int(num_inflections)


def get_drop_contact_points(contour: np.ndarray, side: str, num_inflections: int):
    y, x = contour.T
    if side.lower() not in ['left', 'right']:
        raise ValueError
    
    if num_inflections > 1:
        if side.lower() == 'left':
            col = np.max(x)
        else:
            col = np.min(x)
    else:
        if side.lower() == 'left':
            col = np.min(x)
        else:
            col = np.max(x)

    mask: np.ndarray = x == col
    #print(y[mask])
    return contour[mask.T]


def partition_main_contour(img: np.ndarray, contour: np.ndarray, baseline_row: int):
    assert contour.shape[1] == 2

    mask = contour[:, 0] < baseline_row
    drop_contour = contour[mask]

    STEP_INTERVAL: int = 10
    idx_mid: int = len(drop_contour) // 2
    left_contour_sample = drop_contour[idx_mid:0:-STEP_INTERVAL, :]
    right_contour_sample = drop_contour[idx_mid::STEP_INTERVAL, :]
    # print(right_contour_sample)
    # print(left_contour_sample)

    contact_points = []
    for side, half_contour in zip(['left', 'right'], [left_contour_sample, right_contour_sample]):
        y, x = half_contour.T
        #gradient = np.gradient(x)
        idx_inflection, num_inflections = find_inflection_point(half_contour)

        if side == 'left':
            idx = idx_mid - idx_inflection * STEP_INTERVAL
            idx_min = max(idx - STEP_INTERVAL, 0)
            idx_max = idx + STEP_INTERVAL
        else:
            idx = idx_mid + idx_inflection * STEP_INTERVAL
            idx_min = idx - STEP_INTERVAL
            idx_max = min(idx + STEP_INTERVAL, len(drop_contour))
        
        neighborhood = drop_contour[idx_min:idx_max, :]
        #print(neighborhood)
        #print(num_inflections)
        contact_points.append(get_drop_contact_points(neighborhood, side, num_inflections))

    #fig, axes = plt.subplots(nrows=1, ncols=2, figsize=(10, 6))
    #axes[0].imshow(img, cmap='Greys_r')
    #axes[0].scatter(left_contour_sample.T[1], left_contour_sample.T[0], s=5)
    #axes[0].scatter(right_contour_sample.T[1], right_contour_sample.T[0], s=5)
    #print(rows)
    
    rows = [cp[:, 0] for cp in contact_points]
    rows_intersect = np.intersect1d(*rows)
    row_contact_points = -1
    cps = []
    if len(rows_intersect) == 0:
        rows_concat = np.concatenate((*rows,))
        row_contact_points = math.floor(np.median(rows_concat))
        
        
        #print('!!!!! UNEVEN !!!!!')
        print(*rows, sep='\n')
        cp1, cp2 = contact_points[0], contact_points[1]
        mid_rows = [np.median(row) for row in rows]
        for mid_row, row, cp in zip(mid_rows, rows, contact_points):
            if mid_row not in row:
                diff = np.absolute(row - mid_row)
                argmin = np.argmin(diff)
                mid_row = row[argmin]
            mask = row == mid_row
            cps.append(cp[mask][0])
        
        cp_idx = []
        for cp in cps:
            cp_idx.append(np.argmax(np.logical_and(contour[:, 0] == cp[0], contour[:, 1] == cp[1])))

        cp1, cp2 = cps
        slope = (cp1[0] - cp2[0]) / (cp2[1] - cp1[1])
        #print(cp1, cp2)
        #print(slope)

        incline = math.atan(slope)
        
        return contour[cp_idx[0]:cp_idx[1], :], incline
        
    else:
        print(rows_intersect)
        row_contact_points = math.floor(np.median(rows_intersect))

    mask = drop_contour[:, 0] <= row_contact_points
    main_drop_contour = drop_contour[mask]
    #axes[1].imshow(img, cmap='Greys_r')
    #axes[1].plot((main_drop_contour.T)[1], (main_drop_contour.T)[0])

    #plt.show()
    #plt.close()

    #print(main_drop_contour)
    return main_drop_contour, 0

def raise_preprocessing(img: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    img_shape: Tuple[int, int] = img.shape
    
    img_gray: np.ndarray | None = None
    if len(img_shape) == 3:
        img_gray = color.rgb2gray(img)
    else:
        img_gray = img

    # Gamma correction
    img_gamma = exposure.adjust_gamma(img_gray, gamma=2)

    # Gaussian blur
    img_blur = filters.gaussian(img_gamma, sigma=1, preserve_range=False)
    img_blur = exposure.rescale_intensity(img_blur, out_range='uint8')

    img_crop = crop_image(img_blur)

    # Rescale image to be 1000x1000
    max_dim = max(img_crop.shape)
    img_rescaled = transform.rescale(img_crop, 1000 / max_dim, order=3)

    img_processed, baseline_row = set_baseline(img_rescaled)
    #print(img_processed.shape, img_processed.dtype)

    # Get the main contour of the processed image
    main_contour = get_main_contour(img_processed)
    #print(main_contour)
    #print(baseline_row)

    # Partition main contour
    main_drop_contour, incline_rad = partition_main_contour(img_processed, main_contour, baseline_row=baseline_row)

    
    if incline_rad != 0:
        incline_deg = incline_rad * 180 / math.pi
        rotation_matrix = np.array([[math.cos(-incline_rad), math.sin(-incline_rad)],
                                    [-math.sin(-incline_rad), math.cos(-incline_rad)]])
        img_processed = transform.rotate(img_processed, angle=-incline_deg, center=(0, 0), order=3)
        main_contour = main_contour @ rotation_matrix
        main_drop_contour = main_drop_contour @ rotation_matrix
    

    return img_processed, main_contour[:, ::-1], main_drop_contour[:, ::-1]

def measure_contact_angle(fname_input: str, fname_output: str) -> Tuple[float, float]:
    print('Reading input image...')
    img = io.imread(fname_input, as_gray=False)
    
    img_processed = None
    try:
        print('Preprocessing image...')
        
        contact_angle = np.nan
        rmse = np.nan

        
        img_processed, contour, drop_contour = raise_preprocessing(img)

        # Try preprocessing by conan-ml if the RAISE preprocessing fails.
        if contour is None:
            contour = extract_edges_CV(img_processed)
            drop_contour, contact_points = prepare_hydrophobic(contour)

        print('Measuring contact angle...')
        YL_angles, YL_Bo, YL_baselinewidth, YL_volume, YL_shape, YL_baseline, YL_errors, sym_errors, YL_timing = YL_fit(drop_contour)
        
        contact_angle = round(YL_angles[0], 3)
        rmse = round(YL_errors['RMSE'], 3)
        
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.imshow(img_processed, cmap='Greys_r')
        ax.plot(contour[:, 0], contour[:, 1], 'r', label='Main_Contour')
        ax.plot(drop_contour[:, 0], drop_contour[:, 1], 'b', label='Drop_Contour')
        ax.plot(YL_shape[:, 0], YL_shape[:, 1], 'g', label='Fitted_Curve')
        ax.plot(YL_baseline[:, 0], YL_baseline[:, 1], 'm', label='Fitted_Baseline')
        ax.legend(title='Legend')
        #ax.axis('equal')
        ax.set_title(f'Static Contact Angle: {contact_angle} Degrees', loc='left')
        ax.set_title(f'RMSE: {rmse}', loc='Right')
        print('Saving result image...')
        fig.savefig(fname_output, dpi=300)

    except:
        fig, ax = plt.subplots(figsize=(10, 6))
        if img_processed is None:
            ax.imshow(img, cmap='Greys_r')
        else:
            ax.imshow(img_processed, cmap='Greys_r')
        ax.axis('equal')
        print('Saving result image...')
        fig.savefig(fname_output, dpi=300)
    #plt.show()
    finally:
        plt.close()
    return contact_angle, rmse
    
def analyze_data(connection: Connection, event: Event):
    while True:
        msg: str = connection.recv()
        assert isinstance(msg, str)

        output_file = None
        if msg == 'START_EXPERIMENT':
            fname: str = connection.recv()
            assert isinstance(fname, str)
            print(f'Opening new file: {fname}')
            output_file = open(fname, mode='w')

            dir_name: str = connection.recv()
        
        if msg == 'TERMINATE':
            break

        assert output_file is not None
        contact_angle_lst: List[float] = []
        with output_file:
            # Record experiment start time
            date_now = datetime.now()
            start_time = date_now.strftime("%Y-%m-%d %H:%M")
            output_file.write(f'EXPERIMENT_START_TIME,{start_time}\n')

            # Write main headers
            output_file.write('INPUT_FILENAME,OUTPUT_FILENAME,TARGET_CONCENTRATION,FORMULATION,ENTRY_ID,CONTACT_ANGLE,RMSE\n')
            while True:
                msg = connection.recv()
                if isinstance(msg, str):
                    if msg == 'END_EXPERIMENT':
                        # Record the mean and std of the contact angle
                        contact_angle_array = np.array(contact_angle_lst)
                        contact_angle_mean, contact_angle_std = np.nanmean(contact_angle_array), np.nanstd(contact_angle_array)
                        output_file.write(f'CONTACT_ANGLE_AVG,{contact_angle_mean}\n')
                        output_file.write(f'CONTACT_ANGLE_STD,{contact_angle_std}\n')

                        # Record experiment start time
                        date_now = datetime.now()
                        end_time = date_now.strftime("%Y-%m-%d %H:%M")
                        output_file.write(f'EXPERIMENT_START_TIME,{end_time}')
                        break
                else: # if msg is tuple of experiment details
                    assert isinstance(msg, tuple)

                    fname_input, dest_slot, dest_well_name, counter, entry_id, target_concentration, experimental_params = msg
                    fname_output = f'{dir_name}{dest_slot}-{dest_well_name}-{counter}-RESULT.jpg'

                    # Measure contact angle
                    contact_angle, rmse = measure_contact_angle(fname_input, fname_output)
                    # Append contact angle to list
                    contact_angle_lst.append(contact_angle)

                    # Write data entry
                    result = f'{fname_input},{fname_output},{target_concentration},{experimental_params},{entry_id},{contact_angle},{rmse}\n'
                    print(result)
                    assert output_file.write(result) == len(result)

        # Calculate mean and std of contact angles
        contact_angle_array = np.array(contact_angle_lst)
        contact_angle_mean, contact_angle_std = np.nanmean(contact_angle_array), np.nanstd(contact_angle_array)

        connection.send((contact_angle_mean, contact_angle_std))
        event.set()

    return

if __name__ == '__main__':
    print('Contact Angle Analyzer.')
    for fname in ['./TEST_IMAGES/1-D2.jpg']:
        measure_contact_angle(fname, './TEST_IMAGES/1-A1-RESULT.jpg')