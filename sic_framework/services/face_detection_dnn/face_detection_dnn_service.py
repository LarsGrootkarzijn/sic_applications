import cv2
import numpy as np
import torch
import torchvision

from numpy import array

from sic_framework.core import sic_logging
from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import CompressedImageMessage, SICMessage, BoundingBox, BoundingBoxesMessage, \
    SICConfMessage
from sic_framework.core.service_python2 import SICService
from sic_framework.services.face_detection_dnn import attempt_load, scale_coords, xyxy2xywh
from sic_framework.services.face_detection_dnn import non_max_suppression


class DNNFaceDetectionConf(SICConfMessage):
    def __init__(self, conf_threshold: float = .2, iou_threshold: float = .5, classes=None, agnostic_nms=False):
        """
        :param conf_threshold       model class confidence threshold
        :param iou_threshold        non-maximum suppression intersection-over-union threshold
        :param classes              filter by class [0], or [0, 2, 3]. Default=[0]
        :param agnostic_nms         class-agnostic NMS
        """
        SICConfMessage.__init__(self)

        if classes is not None:
            self.classes = [0]

        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.classes = classes
        self.agnostic_nms = agnostic_nms

        self.augment = False
        self.kpt_label = 5





class DNNFaceDetectionService(SICService):

    COMPONENT_STARTUP_TIMEOUT = 10

    def __init__(self, *args, **kwargs):
        super(DNNFaceDetectionService, self).__init__(*args, **kwargs)

        # Initialize face recognition data
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'

        self.model = attempt_load("yolov7-face.pt", map_location=self.device)  # load FP32 model

        stride = int(self.model.stride.max())  # model stride

        self.tf = torchvision.transforms.ToTensor()




    @staticmethod
    def get_inputs():
        return [CompressedImageMessage]

    @staticmethod
    def get_output():
        return BoundingBoxesMessage

    def get_conf(self):
        return DNNFaceDetectionConf()


    def execute(self, inputs):
        image = inputs.get(CompressedImageMessage).image

        original_shape = image.shape


        face_tensor = self.tf(image)[np.newaxis, ...].to(self.device)

        pred = self.model(face_tensor, augment=self.params.augment)[0]
        # Apply NMS
        pred = non_max_suppression(pred, self.params.conf_threshold, self.params.iou_threshold,
                                   classes=self.params.classes, agnostic=self.params.agnostic_nms,
                                   kpt_label=self.params.kpt_label)

        # list of detections, on (n,6) tensor per image [xyxy, conf, cls]

        faces = []


        h, w, c = original_shape
        gn = torch.tensor(original_shape)[[1, 0, 1, 0]].to(self.device)  # normalization gain whwh
        gn_lks = torch.tensor(original_shape)[[1, 0, 1, 0, 1, 0, 1, 0, 1, 0]].to(self.device)  # normalization gain landmarks

        if pred is not None:
            # batch should be one
            det = pred[0]

            # scale_coords(image.shape[2:], det[:, :4], original_shape, kpt_label=False)
            # scale_coords(image.shape[2:], det[:, 6:], original_shape, kpt_label=self.params.kpt_label, step=3)

            for j in range(det.size()[0]): # for every detection in the image
                xywh = (xyxy2xywh(det[j, :4].view(1, 4)) / gn).view(-1)
                xywh = xywh.data.cpu().numpy()
                conf = det[j, 4].cpu().numpy()
                # TODO incorrect
                # landmarks = (det[j, 5:15].view(1, 10) / gn_lks).view(-1).tolist()
                class_num = det[j, 5].cpu().numpy()
                x1 = int(xywh[0] * w - 0.5 * xywh[2] * w)
                y1 = int(xywh[1] * h - 0.5 * xywh[3] * h)
                w2 = int(xywh[2] * w)
                h2 = int(xywh[3] * h)
                bbox = BoundingBox(x1, y1, w2, h2, identifier=class_num, confidence=conf)
                faces.append(bbox)


        return BoundingBoxesMessage(faces)


class DNNFaceDetection(SICConnector):
    component_class = DNNFaceDetectionService


if __name__ == '__main__':
    mod= DNNFaceDetectionService()
    mod._start()
    # SICComponentManager([DNNFaceDetectionService])